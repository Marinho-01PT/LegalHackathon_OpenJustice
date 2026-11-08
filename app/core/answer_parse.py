"""Turn whatever markdown the model returns into display blocks. Pure Python, no LLM, no protocol format required.

Why: models like to answer with wide markdown tables and bullet lists inside cells. Markdown cannot hold lists in
table cells, so they break into stray rows and the table becomes unreadable in a narrow column. Here we repair
those tables and turn every row into a card, split the text into sections, and pull out deadline sentences.

parse(text) -> Parsed(summary, deadlines, sections); each section has blocks:
  ("text", markdown) | ("cards", [Card]) | ("note", text)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
_BOLD_LINE = re.compile(r"^\s*\*\*([^*]{3,90})\*\*:?\s*$")          # a line that is only bold text = heading
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_BULLET_SPLIT = re.compile(r"\s*(?:<br\s*/?>|[•▪◦●]|(?<=\S)\s-\s(?=[A-ZÄÖÜ]))\s*")
_ART = re.compile(r"Art\.?\s*\d+[a-z]?(?:\s*Abs\.?\s*\d+)?(?:\s*lit\.?\s*[a-z])?\s*(?:OR|ZGB|ZPO|VMWG|BV|SchKG)\b")
_DEADLINE = re.compile(r"\d+\s*(Tage|Tagen|Wochen|Monate|Monaten|Jahre|Jahren)\b|\binnert\b|\bspätestens\b|\bbinnen\b|"
                       r"\bunverzüglich\b|\bfristlos\b|angemessene\w* Frist|\bFrist\w*\b.*\bArt\.", re.I)
_GREETING = re.compile(r"^\s*(sehr geehrte\w*|guten tag|hallo|liebe\w*|grüezi|grüß|grüss)\b[^.\n]{0,60}[,!]?\s*$", re.I)
_SIGNOFF = re.compile(r"^\s*(mit freundlichen grü\w+|freundliche grü\w+|beste grü\w+|herzliche grü\w+)\b.*$", re.I | re.S)


def _strip_letter(t: str) -> str:
    lines = (t or "").splitlines()
    while lines and (not lines[0].strip() or _GREETING.match(lines[0])):
        lines.pop(0)
    out = []
    for l in lines:
        if _SIGNOFF.match(l):
            break
        out.append(l)
    t = "\n".join(out).strip()
    return t[:1].upper() + t[1:] if t else t          # "nach Art. 259 OR …" after a removed greeting


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])")


@dataclass
class Card:
    title: str
    kind: str = "other"                                    # remedy: first column is a list of legal remedies
    refs: list[str] = field(default_factory=list)          # "Art. 259a Abs. 1 OR"
    fields: list[tuple[str, list[str]]] = field(default_factory=list)   # (column header, bullet texts)


@dataclass
class Section:
    title: str
    blocks: list[tuple[str, object]] = field(default_factory=list)
    kind: str = "normal"                                   # normal | deadline | disclaimer


@dataclass
class Parsed:
    summary: str = ""
    summary_from_text: bool = False          # True: summary = first paragraph (do not repeat it below)
    deadlines: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)      # short "what you can do" list for the compact view


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _bullets(cell: str) -> list[str]:
    parts = [p.strip(" -*·").strip() for p in _BULLET_SPLIT.split(cell or "")]
    return [p for p in parts if p]


def table_to_cards(lines: list[str]) -> list[Card]:
    rows = [_cells(l) for l in lines if not _TABLE_SEP.match(l)]
    if len(rows) < 2:
        return []
    head, body = rows[0], rows[1:]
    n = len(head)
    cards: list[Card] = []
    for r in body:
        r = (r + [""] * n)[:n]
        filled = [c for c in r if c]
        if not filled:
            continue
        # continuation row: only one cell filled (a bullet that escaped its cell) -> belongs to the previous card
        if cards and len(filled) == 1 and (not r[0] or len(r[0]) > 40 or r[0][:1] in "•▪-*" or r[0] == filled[0]):
            text = _bullets(filled[0]) or [filled[0]]
            target = cards[-1].fields[-1][1] if cards[-1].fields else None
            if target is not None:
                target.extend(text)
            else:
                cards[-1].fields.append(("Hinweise", text))
            continue
        card = Card(title=re.sub(r"\*\*", "", r[0]).strip() or "–",
                    kind="remedy" if re.search(r"rechtsbehelf|möglichkeit|massnahme|maßnahme|recht|option|anspruch",
                                               head[0], re.I) else "other")
        for h, c in zip(head[1:], r[1:]):
            if not c:
                continue
            card.refs += [m.group(0) for m in _ART.finditer(c) if m.group(0) not in card.refs]
            card.fields.append((re.sub(r"\*\*", "", h).strip(), _bullets(c) or [c]))
        cards.append(card)
    # a column that only repeats the article reference is redundant with the chips
    for card in cards:
        keep = []
        for h, b in card.fields:
            rest = _ART.sub("", " ".join(b)).strip(" ,;()")
            if len(rest) < 25 and (card.refs and (_ART.search(" ".join(b)) or "rechtsgrundlage" in h.lower())):
                continue
            keep.append((h, b))
        card.fields = keep
    return cards


def _kind(title: str) -> str:
    t = title.lower()
    if re.search(r"\bfrist(en)?\b|deadline|termine", t):
        return "deadline"
    if t.startswith(("hinweis", "disclaimer", "haftung")):
        return "disclaimer"
    return "normal"


_ABBR = ("z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "bzw.", "ca.", "Art.", "Abs.", "lit.", "Ziff.", "Nr.", "vgl.",
         "S.", "Bst.", "evtl.", "inkl.", "max.", "min.", "resp.", "sog.", "Fr.", "CHF.")


def sentences(text: str) -> list[str]:
    """Sentences, split inside cells/bullets/lines first, abbreviations protected."""
    units = re.split(r"\n|\||<br\s*/?>|[•▪◦●]", re.sub(r"[*#]", "", text or ""))
    out = []
    for u in units:
        u = re.sub(r"\s+", " ", u).strip(" -:")
        if not u or _TABLE_SEP.match(u):
            continue
        for i, a in enumerate(_ABBR):
            u = u.replace(a, f"\x00{i}\x00")
        for part in _SENT.split(u):
            part = re.sub(r"\x00(\d+)\x00", lambda m: _ABBR[int(m.group(1))], part).strip()
            if part:
                out.append(part)
    return out


def parse(text: str) -> Parsed:
    # a bold line that stands on its own is the model's conclusion: it goes into the summary card, not the body
    concl = next((m.group(1).strip() for m in re.finditer(r"^\s*\*\*([^*\n]{40,300})\*\*\s*$", text or "", re.M)
                  if not _GREETING.match(m.group(1))), "")
    if concl:
        text = re.sub(r"^\s*\*\*" + re.escape(concl) + r"\*\*\s*$", "", text, count=1, flags=re.M)
    out = Parsed()
    cur = Section("")
    out.sections.append(cur)
    buf: list[str] = []
    table: list[str] = []

    def flush_text():
        t = "\n".join(buf).strip()
        if t:
            cur.blocks.append(("text", t))
        buf.clear()

    def flush_table():
        if table:
            cards = table_to_cards(table)
            cur.blocks.append(("cards", cards) if cards else ("text", "\n".join(table)))
            table.clear()

    for line in (text or "").splitlines():
        if _TABLE_ROW.match(line) or (table and _TABLE_SEP.match(line)):
            flush_text()
            table.append(line)
            continue
        flush_table()
        m = _HEADING.match(line) or _BOLD_LINE.match(line)
        if m:
            flush_text()
            title = (m.group(2) if m.re is _HEADING else m.group(1)).replace("⚠", "").strip().rstrip(":")
            cur = Section(title, kind=_kind(title))
            out.sections.append(cur)
            continue
        buf.append(line)
    flush_table()
    flush_text()
    out.sections = [s for s in out.sections if s.blocks or s.title]

    # summary: the model's bold conclusion if there is one, else the first real prose paragraph.
    # Letter-style greetings / sign-offs ("Sehr geehrter Mieter,") are dropped from the answer entirely.
    for sec in out.sections:
        sec.blocks = [(k, _strip_letter(b)) if k == "text" else (k, b) for k, b in sec.blocks]
        sec.blocks = [(k, b) for k, b in sec.blocks if k != "text" or b.strip()]
    bold = [concl] if concl else []
    if bold:
        out.summary = bold[0].rstrip(":")
        out.summary_from_text = False

    else:
        first = next((b for s in out.sections[:2] for b in s.blocks if b[0] == "text"), None)
        if first:
            para = re.sub(r"[*_#>]", "", first[1].split("\n\n")[0]).strip()
            if len(para) > 40 and not para.lstrip().startswith(("-", "1.")):
                out.summary = " ".join(sentences(para)[:2])
                out.summary_from_text = True

    # summary: drop lead-in labels and keep it to two sentences
    out.summary = re.sub(r"^(vorab|fazit|zusammenfassung|kurz gesagt|ergebnis)\s*:\s*", "", out.summary, flags=re.I)
    out.summary = " ".join(sentences(out.summary)[:2])

    # actions: remedies from tables, else the first bullet list of the answer (max. 5, one sentence each)
    remedy_tables = [b for sec in out.sections for k, b in sec.blocks if k == "cards" and b and b[0].kind == "remedy"]
    cards = [c for b in remedy_tables for c in b]
    if cards:
        for c in cards[:5]:
            first = next((x for _, items in c.fields for x in items), "")
            ref = f" ({c.refs[0]})" if c.refs else ""
            out.actions.append(f"**{c.title}**{ref}" + (f": {sentences(first)[0]}" if first else ""))
    else:
        for line in (text or "").splitlines():
            m = re.match(r"^\s*(?:[-*•▪]|\d+[.)])\s+(.*)", line)
            if not m:
                if out.actions and line.strip():
                    break                                   # first list ended
                continue
            item = re.sub(r"\*\*", "", m.group(1)).strip()
            label, _, rest = item.partition(":")
            body = sentences(rest)[0] if rest and len(label) < 45 else sentences(item)[0]
            out.actions.append(f"**{label.strip()}**: {body}" if rest and len(label) < 45 else body)
            if len(out.actions) >= 5:
                break
        if not out.actions:                                 # no list either: any table, one line per row
            for c in [c for sec in out.sections for k, b in sec.blocks if k == "cards" for c in b][:5]:
                first = next((x for _, items in c.fields for x in items), "")
                out.actions.append(f"**{c.title}**" + (f": {sentences(first)[0]}" if first else ""))

    # deadline sentences anywhere in the answer, quoted verbatim (max. 3)
    seen = set()
    for sent in sentences(text):
        s = sent
        if 15 < len(s) < 260 and _DEADLINE.search(s) and s.lower() not in seen and s.rstrip(".") not in out.summary:
            seen.add(s.lower())
            out.deadlines.append(s)
        if len(out.deadlines) >= 3:
            break
    # no repetition: a point already shown under deadlines is not repeated under actions
    def _plain(x):
        return re.sub(r"[*:]", "", x).lower().replace(" ", "")
    dl = [_plain(d)[-60:] for d in out.deadlines]
    out.actions = [a for a in out.actions if not any(d and d in _plain(a) for d in dl)]
    return out


def to_markdown(p: Parsed, heading: str = "") -> str:
    """Full answer as plain markdown, tables flattened to bullet lists (for the 'Ganze Antwort' view)."""
    parts = []
    for sec in p.sections:
        if sec.kind == "disclaimer":
            continue
        if sec.title:
            parts.append(f"{heading} {sec.title}" if heading else f"**{sec.title}**")
        for kind, block in sec.blocks:
            if kind == "cards":
                parts.append("\n".join(
                    f"- **{c.title}**" + (f" ({', '.join(c.refs)})" if c.refs else "") + ": "
                    + " ".join(x for _, items in c.fields for x in items) for c in block))
            else:
                # side notes in blockquotes ("> Praktischer Tipp: …") are left out to keep the answer short
                parts.append("\n".join(l for l in block.splitlines() if not l.lstrip().startswith(">")).strip())
    return "\n\n".join(x for x in parts if x.strip())
