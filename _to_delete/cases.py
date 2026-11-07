"""Fälle vergleichen: the Subchallenge 1 result. Every dev case runs without and with the protocol."""
from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from app.core.config import ROOT
from app.core.content import load_dev_cases
from app.core.sources import valid_rate
from app.ui import components as ui
from app.ui import state, theme


def _pct(x):
    return "–" if x is None else f"{x:.0%}"


def _run_all(cases, default_pid: str, model: str) -> list[dict]:
    svc = state.service()
    known = {p["id"] for p in state.protocols(state.settings().cache_key)}
    rows, bar = [], st.progress(0.0, text="Fälle werden geprüft …")
    for i, c in enumerate(cases):
        pid = c.protocol_id if c.protocol_id in known else default_pid
        prompt = c.prompt_block()
        with ThreadPoolExecutor(max_workers=2) as ex:
            fp = ex.submit(svc.run_protocol_unattended, pid, model, prompt)
            fd = ex.submit(svc.run_direct, model, prompt)
            p, d = fp.result(), fd.result()
        hit = None if not c.expected_outcome else c.expected_outcome in (p.outcome_id, p.outcome_label)
        rows.append({"case": c.__dict__, "pid": pid, "protocol": p, "direct": d, "hit": hit})
        bar.progress((i + 1) / len(cases), text=f"{i + 1} von {len(cases)} Fällen geprüft")
    bar.empty()
    out = ROOT / "results" / "app"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"vergleich_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    f.write_text(json.dumps([{**r, "protocol": r["protocol"].to_dict(), "direct": r["direct"].to_dict()} for r in rows],
                            ensure_ascii=False, indent=2), encoding="utf-8")
    st.session_state["bench_file"] = str(f.relative_to(ROOT))
    return rows


def render() -> None:
    theme.head("Fälle vergleichen",
               "Jeder Fall läuft zweimal auf demselben Modell: einmal ohne und einmal mit Prüfschema. "
               "So wird sichtbar, was das Prüfschema an der Antwort ändert.")
    cases = load_dev_cases()
    if not cases:
        st.info("Noch keine Fälle. Legen Sie JSON-Dateien in data/cases/dev/ ab (Format wie dummy_001.json).")
        return
    pid, model = state.selection()
    ids = [c.id for c in cases]
    chosen = st.multiselect("Fälle", ids, default=ids)
    st.caption("Fehlende Angaben werden hier automatisch als «nicht bekannt» beantwortet, damit alle Fälle gleich laufen. "
               "Testfälle aus data/cases/test werden nie geladen.")
    if st.button("Vergleich starten", type="primary", disabled=not (chosen and pid and model)):
        st.session_state["bench"] = _run_all([c for c in cases if c.id in chosen], pid, model)

    rows = st.session_state.get("bench")
    if not rows:
        return
    st.divider()
    hits = [r["hit"] for r in rows if r["hit"] is not None]
    m1, m2, m3 = st.columns(3)
    m1.metric("Richtiges Ergebnis mit Prüfschema", f"{sum(hits)} von {len(hits)}" if hits else "–")
    vr_d = [v for v in (valid_rate(r["direct"].answer) for r in rows) if v is not None]
    vr_p = [v for v in (valid_rate(r["protocol"].answer) for r in rows) if v is not None]
    m2.metric("Gültige Zitate ohne / mit", f"{_pct(sum(vr_d) / len(vr_d) if vr_d else None)} / "
                                            f"{_pct(sum(vr_p) / len(vr_p) if vr_p else None)}")
    td, tp = sum(r["direct"].total_tokens for r in rows), sum(r["protocol"].total_tokens for r in rows)
    m3.metric("Tokens ohne / mit", f"{ui.num(td)} / {ui.num(tp)}")

    st.dataframe([{
        "Fall": r["case"]["id"],
        "Erwartet": r["case"].get("expected_outcome") or "–",
        "Ergebnis mit Prüfschema": r["protocol"].outcome_label or ("Fehler" if r["protocol"].error else "–"),
        "Treffer": {True: "✓", False: "✕", None: "–"}[r["hit"]],
        "Zitate gültig ohne": _pct(valid_rate(r["direct"].answer)),
        "Zitate gültig mit": _pct(valid_rate(r["protocol"].answer)),
        "Tokens ohne": r["direct"].total_tokens,
        "Tokens mit": r["protocol"].total_tokens,
    } for r in rows], hide_index=True, width="stretch")
    if st.session_state.get("bench_file"):
        st.caption(f"Gespeichert unter {st.session_state['bench_file']}")

    st.subheader("Einzelfall ansehen")
    pick = st.selectbox("Fall", [r["case"]["id"] for r in rows], label_visibility="collapsed")
    r = next(x for x in rows if x["case"]["id"] == pick)
    c = r["case"]
    with st.container(border=True):
        st.markdown(f"**Sachverhalt.** {c['facts']}")
        st.markdown(f"**Frage.** {c['question']}")
        if c.get("reference_analysis"):
            st.markdown(f"**Referenzantwort.** {c['reference_analysis']}")
    a, b = st.columns(2, gap="large")
    with a:
        ui.arm_title("Ohne Prüfschema", model or "")
        ui.answer(r["direct"], f"bd-{pick}")
        ui.sources(r["direct"])
        ui.usage(r["direct"])
    with b:
        ui.arm_title("Mit Prüfschema", model or "")
        ui.outcome(r["protocol"])
        t1, t2, t3, t4 = st.tabs(["Antwort", "Prüfpfad", "Zitierte Artikel", "LLM-Aufrufe"])
        with t1:
            ui.answer(r["protocol"], f"bp-{pick}")
        with t2:
            ui.path(r["protocol"])
        with t3:
            ui.sources(r["protocol"])
        with t4:
            ui.traces(r["protocol"], f"bp-{pick}")
        ui.usage(r["protocol"])
