"""Follow-up actions offered after an answer. Each action = one Apertus call with its own system prompt.

Add an action: append an Action to ACTIONS (+ a renderer in app/ui/components.py). The UI shows one button each.
  backend "publicai"     Apertus via Public AI (falls back to OpenJustice without PUBLICAI_API_KEY)
  backend "openjustice"  OpenJustice agent endpoint, optionally with server-side tools (web_search, ...)
  context "case"         sends facts, question, Prüfpfad and answer
  context "area"         sends only legal area and place (no case details leave the app, e.g. for web search)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .models import RunResult

EMAIL_SYSTEM = """Du verfasst für eine Mieterin oder einen Mieter in der Schweiz eine E-Mail an die Vermietung
(Vermieter oder Verwaltung). Grundlage sind ausschliesslich der Sachverhalt, die Frage und die rechtliche
Einschätzung unten.

Regeln:
- Sachlich, höflich und bestimmt. Schweizer Rechtschreibung (ss statt ß), Anrede mit «Sie».
- Erfinde keine Tatsachen, Daten, Beträge oder Namen. Fehlt etwas, setze einen Platzhalter in eckigen
  Klammern, z. B. [Ihr Name], [Adresse der Wohnung], [Datum des Schreibens].
- Nenne die einschlägigen Gesetzesartikel aus der Einschätzung, aber nur diese.
- Formuliere das Anliegen klar (z. B. Bestreitung, Bitte um Begründung, Verlangen des amtlichen Formulars)
  und setze, wo sinnvoll, eine angemessene Antwortfrist.
- Laufende gesetzliche Fristen (z. B. zur Anfechtung bei der Schlichtungsbehörde) werden durch die E-Mail nicht
  gewahrt. Erwähne das nicht in der E-Mail selbst, sondern im Feld "hinweis" für die Mieterin.
- Keine Drohungen, keine Rechtsberatung an die Vermietung, keine Aussagen, die der Mieterin schaden könnten.
- LÄNGE: Der E-Mail-Text hat höchstens 120 Wörter (Anrede und Grussformel eingeschlossen), der Betreff
  höchstens 8 Wörter, der Hinweis genau einen Satz.
- Antworte nur mit dem JSON-Objekt."""

EMAIL_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["betreff", "text", "hinweis"],
    "properties": {"betreff": {"type": "string"}, "text": {"type": "string"}, "hinweis": {"type": "string"}},
}


LAWYER_SYSTEM = """Du hilfst einer Person in der Schweiz, rechtliche Unterstützung zu finden. Suche mit der Websuche
nach konkreten Anlaufstellen für das genannte Rechtsgebiet am genannten Ort (oder im Kanton):
1. die zuständige Schlichtungsbehörde für Miet- und Pachtverhältnisse,
2. die Sektion des Mieterinnen- und Mieterverbands,
3. bis zu drei Anwaltskanzleien oder Anwältinnen/Anwälte, die Mietrecht als Schwerpunkt auf ihrer eigenen
   Website oder im Verzeichnis des kantonalen Anwaltsverbands angeben,
4. falls vorhanden, eine unentgeltliche Rechtsberatung.

Regeln:
- Nimm nur Einträge auf, die du in den Suchergebnissen gefunden hast, jeweils mit der URL der Seite, auf der du sie
  gefunden hast. Erfinde nichts: keine Namen, Adressen, Telefonnummern oder Schwerpunkte aus dem Gedächtnis.
- Kontaktangaben nur, wenn sie auf der gefundenen Seite stehen; sonst leer lassen.
- Keine Rangliste und keine Bewertung («beste», «top»). Reihenfolge: Schlichtungsbehörde, Mieterverband,
  Rechtsberatung, Kanzleien.
- Schweizer Rechtschreibung (ss statt ß).
- LÄNGE: höchstens 5 Einträge insgesamt. «schwerpunkt» höchstens 8 Wörter, «kontakt» nur Telefon oder E-Mail,
  «hinweis» genau ein kurzer Satz. Suche gezielt und höre auf, sobald du genug Einträge hast."""

LAWYER_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["anlaufstellen", "hinweis"],
    "properties": {
        "anlaufstellen": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "art", "ort", "schwerpunkt", "kontakt", "url"],
            "properties": {
                "name": {"type": "string"},
                "art": {"type": "string", "enum": ["Schlichtungsbehörde", "Mieterverband", "Rechtsberatung", "Kanzlei"]},
                "ort": {"type": "string"}, "schwerpunkt": {"type": "string"},
                "kontakt": {"type": "string"}, "url": {"type": "string"}}}},
        "hinweis": {"type": "string"}},
}

JSON_RULE = """

Antworte ausschliesslich mit einem JSON-Objekt mit genau diesen Schlüsseln, ohne Text davor oder danach:
{"betreff": "...", "text": "...", "hinweis": "..."}"""


@dataclass(frozen=True)
class Action:
    id: str
    label: str            # button text: says exactly what happens
    icon: str
    system: str
    schema: dict | None   # strict JSON output, or None for free text
    backend: str = "publicai"
    context: str = "case"
    tools: tuple = field(default=())
    busy: str = "Der Entwurf wird geschrieben …"


ACTIONS = [
    Action("email", "E-Mail an die Vermietung entwerfen", ":material/mail:", EMAIL_SYSTEM, EMAIL_SCHEMA),
    Action("lawyer", "Rechtliche Hilfe in meiner Nähe finden", ":material/gavel:", LAWYER_SYSTEM, LAWYER_SCHEMA,
           backend="openjustice", context="area", tools=("web_search", "web_fetch"),
           busy="Apertus sucht im Web nach Anlaufstellen. Das kann eine Minute dauern …"),
]


def context(facts: str, question: str, jurisdiction: str, res: RunResult) -> str:
    path = "\n".join(f"- {s.label}: {s.value or s.detail[:200]}" for s in res.steps if s.kind != "outcome")
    return (f"JURISDIKTION: {jurisdiction}\n\nSACHVERHALT:\n{facts}\n\nFRAGE:\n{question}\n\n"
            f"ERGEBNIS NACH PRÜFSCHEMA: {res.outcome_label or 'nicht bestimmt'}\n\n"
            f"PRÜFSCHRITTE:\n{path or '-'}\n\nEINSCHÄTZUNG:\n{res.answer}")


def area_context(area: str, place: str, canton: str) -> str:
    return f"RECHTSGEBIET: {area}\nORT: {place or '-'}\nKANTON: {canton}"


def keep_sourced(out: dict) -> dict:
    """Hallucination guard: drop every entry without a source URL."""
    if "anlaufstellen" in out:
        items = out.get("anlaufstellen") or []
        out["anlaufstellen"] = [x for x in items if str(x.get("url", "")).startswith("http")]
        out["verworfen"] = len(items) - len(out["anlaufstellen"])
    return out


def parse(action: Action, text: str) -> dict:
    """JSON for schema actions; tolerant fallback when a model returns prose."""
    if action.schema:
        try:
            s = text.strip()
            m = re.search(r"\{.*\}", s, re.S)          # tolerate fences or a sentence around the JSON
            return json.loads(m.group(0) if m else s)
        except Exception:
            if action.id == "email":
                return {"betreff": "", "text": text, "hinweis": ""}
            return {"anlaufstellen": [], "hinweis": "", "raw": text}
    return {"text": text}
