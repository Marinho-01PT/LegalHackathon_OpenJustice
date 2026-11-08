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


OUT_OF_SCOPE = re.compile(r"ausserhalb|außerhalb|nicht (anwendbar|abgedeckt)|out of scope", re.I)
GENERIC_LABEL = re.compile(r"^\s*(outcome|ergebnis|result|resultat|end|ende|output)\s*\d*\s*$", re.I)
_WARN_HEAD = re.compile(r"achtung|vorkehrung|hinweis|risik|wichtig|vorsicht", re.I)


def answer(res: RunResult, key: str) -> None:
    """Answer as readable blocks: summary, deadlines, one card per remedy. Built by the app from whatever
    markdown the model returns (app/core/answer_parse.py), so it does not depend on the protocol's output format."""
    if res.status == "failed":
        st.error(res.error or "Unbekannter Fehler.")
        return
    if not (res.answer or "").strip():
        st.caption("Keine Antwort erhalten.")
        return
    try:
        _structured(res, key)
    except Exception:                       # never lose an answer because of the layout
        with st.container(key=f"oj-answer-{key}"):
            st.markdown(res.answer)


def _structured(res: RunResult, key: str) -> None:
    """Plain text like the original view, cleaned up: no greeting/sign-off, tables turned into short lists
    (markdown tables with lists inside cells break), headings kept. No boxes, no expander."""
    from app.core.answer_parse import parse, to_markdown
    p = parse(res.answer)
    if res.outcome_label and OUT_OF_SCOPE.search(res.outcome_label):
        st.warning("Diese Frage liegt ausserhalb des Prüfschemas. Wenden Sie sich an den Mieterinnen- und "
                   "Mieterverband (mieterverband.ch) oder die Schlichtungsbehörde Ihres Kantons.")
    label = res.outcome_label or ""
    if label and not GENERIC_LABEL.match(label) and label != res.outcome_id:
        outcome(res)
    with st.container(key=f"oj-answer-{key}"):
        if p.summary and not p.summary_from_text:
            st.markdown(f"**{p.summary}**")             # the model's own bold conclusion, kept at the top
        st.markdown(to_markdown(p, heading="####") or res.answer)
        disclaimer = " ".join(b for sec in p.sections if sec.kind == "disclaimer" for k, b in sec.blocks if k == "text")
        if disclaimer:
            st.caption(disclaimer)


def _cards(cards, key: str) -> None:
    per_row = 3 if len(cards) >= 3 else max(1, len(cards))
    for r in range(0, len(cards), per_row):
        cols = st.columns(per_row, gap="small")
        for col, c in zip(cols, cards[r:r + per_row]):
            with col, st.container(border=True, key=f"oj-card-{key}-{r}-{c.title[:20]}"):
                st.markdown(f"**{c.title}**")
                if c.refs:
                    _ref_chips(c.refs)
                for head, items in c.fields:
                    warn = bool(_WARN_HEAD.search(head))
                    st.markdown(f'<div class="oj-field{" warn" if warn else ""}">{html.escape(head)}</div>',
                                unsafe_allow_html=True)
                    st.markdown("\n".join(f"- {x}" for x in items) if len(items) > 1 else items[0])


def _ref_chips(refs: list[str]) -> None:
    status = {x["ref"]: x for x in check_sources(" ".join(refs))}
    chips = []
    for ref in refs:
        short = re.sub(r"\s*Abs\..*?(?=\s(?:OR|ZGB|ZPO|VMWG|BV|SchKG)\b)", "", ref)   # status is per article
        x = status.get(re.sub(r"\s+", " ", short)) or {"status": "unchecked", "url": None}
        el, tag = ("a", f'href="{x["url"]}" target="_blank"') if x.get("url") else ("span", "")
        chips.append(f'<{el} class="{x["status"]}" {tag}>{html.escape(ref)}</{el}>')
    st.markdown('<div class="oj-src">' + "".join(chips) + "</div>", unsafe_allow_html=True)


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


def next_steps(res: RunResult, run: dict, key: str) -> None:
    """One button per follow-up action (app/core/actions.py); each result is drawn by its renderer below."""
    from app.core.actions import ACTIONS, area_context, context
    from app.ui import state

    if res.status != "completed" or not res.answer:
        return
    cfg, model = state.settings(), run["model"]
    st.markdown("**Wie geht es weiter?**")
    cols = st.columns([1] * len(ACTIONS) + [max(0.2, 3 - len(ACTIONS))])
    for col, a in zip(cols, ACTIONS):
        if col.button(a.label, icon=a.icon, key=f"act-{a.id}-{key}", width="stretch"):
            ctx = (context(run.get("facts", ""), run.get("question", ""), run.get("jurisdiction", "CH"), res)
                   if a.context == "case" else area_context(cfg.legal_area, run.get("place", ""), run.get("canton", "")))
            with st.spinner(a.busy):
                st.session_state[f"act-{a.id}-{key}-out"] = state.service().run_action(
                    a, model, ctx, cfg.publicai_key, cfg.publicai_model)
            for k in (f"mail-subj-{key}", f"mail-body-{key}"):
                st.session_state.pop(k, None)
    for a in ACTIONS:
        out = st.session_state.get(f"act-{a.id}-{key}-out")
        if out:
            if out.get("error"):
                st.error(out["error"])
            else:
                RENDERERS[a.id](out, model, key)


def _email(out: dict, model: str, key: str) -> None:
    from urllib.parse import quote
    with st.container(border=True, key=f"oj-mail-{key}"):
        st.markdown("**Entwurf: E-Mail an die Vermietung**")
        st.caption("Prüfen und ergänzen Sie den Entwurf, besonders die Angaben in [eckigen Klammern]. "
                   "Es wird nichts automatisch versendet.")
        to = st.text_input("An", key=f"mail-to-{key}", placeholder="E-Mail-Adresse der Vermietung")
        subj = st.text_input("Betreff", value=out.get("betreff", ""), key=f"mail-subj-{key}")
        body = st.text_area("Text", value=out.get("text", ""), height=320, key=f"mail-body-{key}")
        if out.get("hinweis"):
            with st.container(key=f"oj-deadline-mail-{key}"):
                st.markdown(f"**Wichtig für Sie:** {out['hinweis']}")
        c1, c2 = st.columns([1, 1])
        c1.link_button("Im E-Mail-Programm öffnen", f"mailto:{quote(to or '')}?subject={quote(subj)}&body={quote(body)}",
                       icon=":material/send:", type="primary", width="stretch")
        with c2.popover("Text kopieren", icon=":material/content_copy:", width="stretch"):
            st.code(f"Betreff: {subj}\n\n{body}", language=None, wrap_lines=True)
        _made_by(out, model)


def _lawyer(out: dict, model: str, key: str) -> None:
    from urllib.parse import urlparse
    with st.container(border=True, key=f"oj-help-{key}"):
        st.markdown("**Anlaufstellen in Ihrer Nähe**")
        st.caption("Bei Streit um die Miete ist die Schlichtungsbehörde meist der erste Schritt: Das Verfahren ist "
                   "kostenlos, und eine anwaltliche Vertretung ist dort nicht nötig.")
        items = out.get("anlaufstellen") or []
        if not items:
            st.info("Die Websuche hat keine Anlaufstellen mit Quelle gefunden. Suchen Sie direkt beim kantonalen "
                    "Anwaltsverband oder beim Mieterinnen- und Mieterverband (mieterverband.ch).")
        for i, x in enumerate(items):
            c1, c2 = st.columns([4, 1.2], vertical_alignment="center")
            line = f"**{x.get('name', '')}**  \n{x.get('art', '')}"
            if x.get("ort"):
                line += f", {x['ort']}"
            if x.get("schwerpunkt"):
                line += f"  \n{x['schwerpunkt']}"
            if x.get("kontakt"):
                line += f"  \n{x['kontakt']}"
            c1.markdown(line)
            c2.link_button(urlparse(x["url"]).netloc.removeprefix("www.") or "Website", x["url"],
                           icon=":material/open_in_new:", width="stretch")
            if i < len(items) - 1:
                st.markdown('<hr style="margin:.3rem 0;border:none;border-top:1px solid var(--line)">',
                            unsafe_allow_html=True)
        if out.get("hinweis"):
            st.caption(out["hinweis"])
        dropped = f"   {out['verworfen']} Einträge ohne Quelle verworfen" if out.get("verworfen") else ""
        st.caption("Gefunden per Websuche, keine Empfehlung und keine Rangliste. Bitte prüfen Sie die Angaben auf "
                   "der verlinkten Seite. Ihr Sachverhalt wurde für die Suche nicht weitergegeben, nur Rechtsgebiet "
                   "und Ort." + dropped)
        _made_by(out, model)


def _made_by(out: dict, model: str) -> None:
    u = out.get("usage") or {}
    st.caption(f"Erstellt von {out.get('model', model)}   {num(u.get('tokens', 0))} Tokens   {u.get('seconds', 0)} s")


RENDERERS = {"email": _email, "lawyer": _lawyer}
