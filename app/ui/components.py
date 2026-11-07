"""Reusable render functions. Each takes a RunResult (or text) and draws one piece of the answer."""
from __future__ import annotations

import html
import json
import re

import streamlit as st

from app.core.models import RunResult
from app.core.sources import check_sources

_HEAD = re.compile(r"^#{1,4}\s+(.+?)\s*$", re.M)


def _esc(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br>")


def num(n: float) -> str:
    return f"{n:,.0f}".replace(",", "’")


def split_sections(text: str) -> list[tuple[str, str]]:
    parts = _HEAD.split(text or "")
    out = [("", parts[0].strip())] if parts[0].strip() else []
    for i in range(1, len(parts), 2):
        out.append((parts[i].strip(), parts[i + 1].strip() if i + 1 < len(parts) else ""))
    return out


def arm_title(title: str, note: str = "") -> None:
    st.markdown(f'<div class="oj-arm">{html.escape(title)}<span>{html.escape(note)}</span></div>',
                unsafe_allow_html=True)


def outcome(res: RunResult) -> None:
    if res.outcome_label:
        st.markdown(f'<div class="oj-outcome"><span class="k">Ergebnis nach Prüfschema</span>'
                    f'<span class="v">{html.escape(res.outcome_label)}</span></div>', unsafe_allow_html=True)


def answer(res: RunResult, key: str) -> None:
    if res.status == "failed":
        st.error(res.error or "Unbekannter Fehler.")
        return
    with st.container(key=f"oj-answer-{key}"):
        sections = split_sections(res.answer)
        if not sections:
            st.caption("Keine Antwort erhalten.")
        for i, (h, body) in enumerate(sections):
            low = h.lower()
            if "frist" in low:
                with st.container(key=f"oj-deadline-{key}-{i}"):
                    st.markdown(f"**{h.replace('⚠', '').strip()}**")
                    st.markdown(body)
            elif low.startswith("hinweis"):
                st.caption(body)
            else:
                if h:
                    st.markdown(f"#### {h}")
                if body:
                    st.markdown(body)


def path(res: RunResult) -> None:
    if not res.steps:
        st.caption("Ohne Prüfschema gibt es keinen Prüfpfad." if res.mode == "direct" else "Noch keine Prüfschritte.")
        return
    rows = []
    for s in res.steps:
        val = f'<span class="val{" no" if s.value == "Nein" else ""}">{html.escape(s.value)}</span>' if s.value else ""
        q = f'<div class="q">{_esc(s.question)}</div>' if s.question else ""
        det = (f'<details><summary>Begründung anzeigen</summary><div class="det">{_esc(s.detail)}</div></details>'
               if s.detail and s.detail.strip() != s.value else "")
        rows.append(f'<div class="oj-step {s.kind}"><span class="lbl">{html.escape(s.label)}</span>{val}{q}{det}</div>')
    if res.status == "in_progress":
        rows.append('<div class="oj-step running"><span class="lbl">Nächster Prüfschritt läuft …</span></div>')
    st.markdown('<div class="oj-path">' + "".join(rows) + "</div>", unsafe_allow_html=True)


def traces(res: RunResult, key: str) -> None:
    """Exact LLM calls per protocol step, loaded on demand (GET .../node_results/{id}/trace)."""
    from app.ui import state
    steps = [s for s in res.steps if s.nr_id and s.response_id]
    if not steps:
        st.caption("Für diesen Lauf sind keine Aufzeichnungen verfügbar.")
        return
    st.caption("Was das Modell in einem Prüfschritt genau bekommen und geantwortet hat (ohne Systemprompt).")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    pick = c1.selectbox("Prüfschritt", range(len(steps)), format_func=lambda i: steps[i].label, key=f"tr-sel-{key}")
    if c2.button("Aufrufe laden", key=f"tr-btn-{key}", width="stretch"):
        s = steps[pick]
        try:
            st.session_state[f"tr-{key}"] = (s.nr_id, state.service().node_trace(s.response_id, s.nr_id))
        except Exception as exc:
            from app.core.service import friendly_error
            st.session_state[f"tr-{key}"] = (s.nr_id, {"error": friendly_error(exc)})
    loaded = st.session_state.get(f"tr-{key}")
    if loaded and loaded[0] == steps[pick].nr_id:
        tr = loaded[1]
        if tr.get("error"):
            st.error(tr["error"])
            return
        calls = tr.get("calls") or []
        st.caption(f"{tr.get('call_count', len(calls))} LLM-Aufruf(e)")
        for i, call in enumerate(calls, 1):
            with st.expander(f"Aufruf {i}", expanded=len(calls) == 1):
                st.json(call, expanded=2)
        if not calls:
            st.json(tr, expanded=2)


def sources(res: RunResult) -> None:
    items = check_sources(res.answer)
    if not items:
        st.caption("Die Antwort nennt keine Gesetzesartikel.")
        return
    chips = []
    for x in items:
        title = {"ok": "Artikel existiert", "missing": "Artikel nicht gefunden",
                 "unchecked": "Nicht geprüft (Gesetzestext nicht hinterlegt)"}[x["status"]]
        tag = f'href="{x["url"]}" target="_blank"' if x["url"] else ""
        el = "a" if x["url"] else "span"
        chips.append(f'<{el} class="{x["status"]}" title="{title}" {tag}>{html.escape(x["ref"])}</{el}>')
    st.markdown('<div class="oj-src">' + "".join(chips) + "</div>", unsafe_allow_html=True)
    st.caption("✓ geprüft gegen den Gesetzestext in data/law · ✕ existiert dort nicht · grau: nicht geprüft. "
               "Ein Klick öffnet den Artikel auf Fedlex.")


def usage(res: RunResult) -> None:
    u = res.usage
    st.caption(f"{num(res.total_tokens)} Tokens   {u.get('seconds', 0):.1f} s   "
               f"{u.get('requests', 0)} API-Anfrage{'n' if u.get('requests', 0) != 1 else ''}")


def raw(res: RunResult) -> None:
    st.code(json.dumps(res.to_dict(), ensure_ascii=False, indent=2), language="json")
