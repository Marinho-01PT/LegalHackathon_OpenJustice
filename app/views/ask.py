"""Frage stellen: one question, answered with the protocol, optionally side by side with the plain model."""
from __future__ import annotations

import datetime as dt

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


def _run(facts: str, question: str, canton: str, place: str, day: dt.date) -> None:
    pid, model = state.selection()
    svc = state.service()
    for k in [k for k in st.session_state if str(k).startswith(("act-", "mail-"))]:
        del st.session_state[k]
    prompt = build_prompt(facts, question, f"CH, Kanton {canton}", day.isoformat())
    res = _live(svc, pid, svc.start(pid, model, prompt))
    st.session_state["ask"] = {"protocol": res, "pid": pid, "model": model,
                               "facts": facts, "question": question, "jurisdiction": f"CH, Kanton {canton}",
                               "canton": canton, "place": place}


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


def _result(res) -> None:
    """Answer in full width; Prüfpfad, sources and LLM calls below in tabs (they no longer squeeze the answer)."""
    ui.answer(res, "ask")
    st.write("")
    n = len([s for s in res.steps if s.kind != "outcome"])
    t1, t2, t3 = st.tabs([f"Prüfpfad ({n} Schritte)", "Zitierte Artikel", "LLM-Aufrufe"])
    with t1:
        st.caption("Diese Schritte des Prüfschemas hat das Modell durchlaufen.")
        ui.path(res)
    with t2:
        ui.sources(res)
    with t3:
        ui.traces(res, "ask")
    ui.usage(res)


def _scope(pid: str | None) -> None:
    """Which topic the selected protocol covers, from APP_SCOPE or the protocol's own name/description."""
    import os
    if not pid:
        return
    scope = os.environ.get("APP_SCOPE", "").strip()
    if not scope:
        info = state.service().protocol_info(pid)
        scope = info.get("description") or info.get("name") or ""
    if scope:
        st.info(f"**Dieses Prüfschema deckt ab:** {scope}  \nFür andere Themen ist die Einschätzung nicht verlässlich. "
                "Wenden Sie sich dann an den Mieterinnen- und Mieterverband oder die Schlichtungsbehörde Ihres Kantons.",
                icon=":material/info:")


def render() -> None:
    s = state.settings()
    autorun = _apply_prefill()
    pid_sel = state.selection()[0]
    proto_name = ""
    if pid_sel:
        try:
            proto_name = state.service().protocol_info(pid_sel).get("name", "")
        except Exception:
            proto_name = ""
    theme.head("Was ist bei Ihnen passiert?",
               "Schildern Sie Ihre Situation in eigenen Worten. Die Einschätzung folgt dem Prüfschema, "
               "das Juristinnen und Juristen in OpenJustice erstellt haben, und zeigt jeden Prüfschritt.",
               eyebrow=f"Prüfschema: {proto_name}" if proto_name else "")

    with st.form("ask_form", border=False):
        facts = st.text_area("Ihre Situation", key="facts", height=150,
                             placeholder="Zum Beispiel: Seit zwei Wochen funktioniert die Heizung im Wohnzimmer nicht mehr. "
                                         "Ich habe es dem Vermieter am 28. Oktober gemeldet, passiert ist nichts.")
        question = st.text_input("Ihre Frage", key="question", placeholder="Was kann ich tun, und brauche ich eine Juristin?")
        c1, c2, c3 = st.columns([1.1, 1.1, 1], vertical_alignment="bottom")
        canton = c1.selectbox("Kanton", CANTONS, index=CANTONS.index("St. Gallen"), key="canton")
        place = c2.text_input("Wohnort (optional)", key="place", placeholder="z. B. Rorschach",
                              help="Wird nur für die Suche nach Anlaufstellen in Ihrer Nähe verwendet.")
        day = c3.date_input("Stichtag", value=dt.date.today(), format="DD.MM.YYYY", key="legal_date")
        submitted = st.form_submit_button("Einschätzung erstellen", type="primary")

    pid, model = state.selection()
    if submitted or autorun:
        if not (facts or "").strip():
            st.warning("Beschreiben Sie zuerst Ihre Situation.")
        elif not pid or not model:
            st.warning("Wählen Sie links ein Prüfschema und ein Modell.")
        else:
            _run(facts, question or "Wie ist die Rechtslage?", canton, place, day)

    run = st.session_state.get("ask")
    if not run:
        return
    st.divider()
    p = run["protocol"]
    if p.status == "awaiting_input":
        _questions(p, run["pid"], run["model"])
    _result(p)
    st.divider()
    ui.next_steps(p, run, "ask")
    with st.expander("Technische Details"):
        ui.raw(p)
    if s.mock:
        st.caption("Demo-Modus: Die Antworten stammen nicht vom Modell.")
