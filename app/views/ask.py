"""Frage stellen: one question, answered with the protocol, optionally side by side with the plain model."""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from app.core.service import build_prompt
from app.ui import components as ui
from app.ui import state, theme

CANTONS = ["Aargau", "Appenzell Ausserrhoden", "Appenzell Innerrhoden", "Basel-Landschaft", "Basel-Stadt", "Bern",
           "Freiburg", "Genf", "Glarus", "Graubünden", "Jura", "Luzern", "Neuenburg", "Nidwalden", "Obwalden",
           "Schaffhausen", "Schwyz", "Solothurn", "St. Gallen", "Tessin", "Thurgau", "Uri", "Waadt", "Wallis",
           "Zug", "Zürich"]


def _apply_prefill() -> bool:
    pre = st.session_state.pop("prefill", None)
    if not pre:
        return False
    st.session_state["facts"] = pre.get("facts", "")
    st.session_state["question"] = pre.get("question", "")
    return True


def _live(svc, pid: str, res):
    """Poll a background run and draw the Prüfpfad as it grows."""
    with st.status("Das Prüfschema wird Schritt für Schritt durchlaufen …", expanded=True) as box:
        ph = st.empty()

        def draw(r):
            with ph.container():
                ui.path(r)
            done = len([s for s in r.steps if s.kind != "outcome"])
            box.update(label=f"Prüfschema läuft: {done} Schritt{'e' if done != 1 else ''} erledigt …")

        draw(res)
        res = svc.wait(pid, res, on_update=draw)
        box.update(label="Prüfschema durchlaufen" if res.status != "failed" else "Lauf abgebrochen",
                   state="error" if res.status == "failed" else "complete", expanded=False)
    return res


def _run(facts: str, question: str, canton: str, day: dt.date, compare: bool) -> None:
    pid, model = state.selection()
    svc = state.service()
    prompt = build_prompt(facts, question, f"CH, Kanton {canton}", day.isoformat())
    with ThreadPoolExecutor(max_workers=1) as ex:
        fd = ex.submit(svc.run_direct, model, prompt) if compare else None
        res = _live(svc, pid, svc.start(pid, model, prompt))
        if fd:
            with st.spinner("Die Antwort ohne Prüfschema wird fertiggestellt …"):
                direct = fd.result()
        else:
            direct = None
    st.session_state["ask"] = {"protocol": res, "direct": direct, "pid": pid, "model": model}


def _questions(res, pid: str, model: str) -> None:
    """The protocol stopped because facts are missing: ask the person instead of guessing."""
    with st.container(border=True):
        st.markdown("**Für eine Einschätzung fehlen noch Angaben**")
        st.caption("Das Prüfschema braucht diese Informationen. Was Sie nicht wissen, können Sie leer lassen.")
        with st.form("pending", border=False):
            answers = {}
            for q in res.pending:
                label = q.question or q.label
                if q.data_type == "boolean":
                    v = st.radio(label, ["Ja", "Nein", "Weiss nicht"], index=2, horizontal=True, key=f"pq-{q.id}")
                    answers[q.id] = "" if v == "Weiss nicht" else v
                elif q.data_type == "date":
                    v = st.date_input(label, value=None, format="DD.MM.YYYY", key=f"pq-{q.id}")
                    answers[q.id] = v.isoformat() if v else ""
                else:
                    answers[q.id] = st.text_input(label, key=f"pq-{q.id}")
            c1, c2 = st.columns([1, 1])
            go = c1.form_submit_button("Angaben senden", type="primary", width="stretch")
            skip = c2.form_submit_button("Ohne diese Angaben weiter", width="stretch")
    svc = state.service()
    if go or skip:
        new = svc.answer_questions(pid, model, res, answers) if go else svc.skip_questions(pid, model, res)
        st.session_state["ask"]["protocol"] = _live(svc, pid, new)
        st.rerun()


def _protocol_arm(res, key: str, wide: bool) -> None:
    ui.outcome(res)
    if wide:
        left, right = st.columns([1.7, 1], gap="large")
        with left:
            ui.answer(res, key)
        with right:
            st.markdown("**Prüfpfad**")
            st.caption("Diese Schritte des Prüfschemas hat das Modell durchlaufen.")
            ui.path(res)
        st.markdown("**Zitierte Artikel**")
        ui.sources(res)
        with st.expander("LLM-Aufrufe je Prüfschritt"):
            ui.traces(res, key)
    else:
        t1, t2, t3, t4 = st.tabs(["Antwort", "Prüfpfad", "Zitierte Artikel", "LLM-Aufrufe"])
        with t1:
            ui.answer(res, key)
        with t2:
            ui.path(res)
        with t3:
            ui.sources(res)
        with t4:
            ui.traces(res, key)
    ui.usage(res)


def render() -> None:
    s = state.settings()
    autorun = _apply_prefill()
    theme.head("Was ist bei Ihnen passiert?",
               "Schildern Sie Ihre Situation in eigenen Worten. Die Einschätzung folgt dem Prüfschema, "
               "das Juristinnen und Juristen in OpenJustice erstellt haben, und zeigt jeden Prüfschritt.")

    with st.form("ask_form", border=False):
        facts = st.text_area("Ihre Situation", key="facts", height=150,
                             placeholder="Zum Beispiel: Mein Vermieter hat mir am 3. Oktober per Brief mitgeteilt, "
                                         "dass die Miete ab Januar um 8 % steigt. Ein Formular lag nicht bei.")
        question = st.text_input("Ihre Frage", key="question", placeholder="Muss ich die Erhöhung anfechten?")
        c1, c2, c3 = st.columns([1.1, 1, 1.4], vertical_alignment="bottom")
        canton = c1.selectbox("Kanton", CANTONS, index=CANTONS.index("St. Gallen"), key="canton")
        day = c2.date_input("Stichtag", value=dt.date.today(), format="DD.MM.YYYY", key="legal_date")
        compare = c3.toggle("Mit Antwort ohne Prüfschema vergleichen", key="compare",
                            help="Dasselbe Modell beantwortet die Frage zusätzlich ohne Prüfschema.")
        submitted = st.form_submit_button("Einschätzung erstellen", type="primary")

    pid, model = state.selection()
    if submitted or autorun:
        if not (facts or "").strip():
            st.warning("Beschreiben Sie zuerst Ihre Situation.")
        elif not pid or not model:
            st.warning("Wählen Sie links ein Prüfschema und ein Modell.")
        else:
            _run(facts, question or "Wie ist die Rechtslage?", canton, day, compare)

    run = st.session_state.get("ask")
    if not run:
        return
    st.divider()
    p, d = run["protocol"], run["direct"]
    if p.status == "awaiting_input":
        _questions(p, run["pid"], run["model"])
    if d is None:
        _protocol_arm(p, "single", wide=True)
    else:
        a, b = st.columns(2, gap="large")
        with a:
            ui.arm_title(f"{run['model']} allein", "ohne Prüfschema")
            t1, t2 = st.tabs(["Antwort", "Zitierte Artikel"])
            with t1:
                ui.answer(d, "direct")
            with t2:
                ui.sources(d)
            ui.usage(d)
        with b:
            ui.arm_title(f"{run['model']} mit Prüfschema", "OpenJustice")
            _protocol_arm(p, "protocol", wide=False)
    with st.expander("Technische Details"):
        ui.raw(p)
        if d:
            ui.raw(d)
    if s.mock:
        st.caption("Demo-Modus: Die Antworten stammen nicht vom Modell.")
