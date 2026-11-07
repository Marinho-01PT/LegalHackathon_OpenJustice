"""Companion, not judge: one shared output frame for every engine + a deterministic completeness check.

The tool orients the person (assessment, deadlines, options, next steps, where to get help).
It never presents itself as a decision. Legal grounding stays in the protocol; only the framing changes.
"""
from __future__ import annotations

import re

DISCLAIMER = ("Hinweis: Dies ist eine Orientierungshilfe, keine Rechtsberatung und kein Entscheid. "
              "Verbindlich entscheiden nur die Schlichtungsbehörde bzw. das Gericht.")

# section key -> heading shown to the user
SECTIONS = {
    "assessment": "Einschätzung",
    "confidence": "Sicherheit der Einschätzung",
    "deadlines": "⚠ Fristen",
    "options": "Ihre Optionen",
    "next_steps": "Nächste Schritte",
    "missing_info": "Fehlende Angaben",
    "seek_help": "Wann Sie sich beraten lassen sollten",
    "disclaimer": "Hinweis",
}

FRAME_INSTRUCTION = f"""Write the answer as an orienting COMPANION for a tenant, not as a judgment:
- State the legal assessment with its sources, but as an assessment ("spricht dafür, dass …"), never as a decision.
- Deadlines are NEVER softened: name each deadline, its legal basis and what happens if it is missed.
- Offer concrete options and next steps (competent authority, forms, documents, costs).
- Name missing information and when to see a tenants' association or a lawyer.
- Use exactly these headings, in this order: {", ".join(SECTIONS.values())}.
- End with: "{DISCLAIMER}" """

# JSON schema part used by the plan engines (structured -> rendered with the headings above)
SCHEMA_PROPS = {
    "assessment": {"type": "string"},
    "confidence": {"type": "string", "enum": ["hoch", "mittel", "unsicher"]},
    "confidence_reason": {"type": "string"},
    "deadlines": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["what", "until", "legal_basis", "if_missed"],
                                             "properties": {"what": {"type": "string"}, "until": {"type": "string"},
                                                            "legal_basis": {"type": "string"}, "if_missed": {"type": "string"}}}},
    "options": {"type": "array", "items": {"type": "string"}},
    "next_steps": {"type": "array", "items": {"type": "string"}},
    "seek_help": {"type": "string"},
}


def render(d: dict, follow_up: list[str]) -> str:
    """Structured companion JSON -> user-facing text with the fixed headings."""
    def bullets(xs):
        return "\n".join(f"- {x}" for x in xs) if xs else "- keine"
    dl = "\n".join(f"- {x['what']}: bis {x['until']} ({x['legal_basis']}). Falls verpasst: {x['if_missed']}"
                   for x in d.get("deadlines", [])) or "- Keine Frist ersichtlich."
    return "\n\n".join([
        f"## {SECTIONS['assessment']}\n{d.get('assessment', '')}",
        f"## {SECTIONS['confidence']}\n{d.get('confidence', '')} – {d.get('confidence_reason', '')}",
        f"## {SECTIONS['deadlines']}\n{dl}",
        f"## {SECTIONS['options']}\n{bullets(d.get('options', []))}",
        f"## {SECTIONS['next_steps']}\n{bullets(d.get('next_steps', []))}",
        f"## {SECTIONS['missing_info']}\n{bullets(follow_up)}",
        f"## {SECTIONS['seek_help']}\n{d.get('seek_help', '')}",
        f"## {SECTIONS['disclaimer']}\n{DISCLAIMER}",
    ])


# ------------------------------------------------------------------ check (no LLM)
_PATTERNS = {
    "assessment": r"einschätzung|assessment",
    "deadlines": r"frist|deadline",
    "options": r"option",
    "next_steps": r"nächste schritte|next steps",
    "missing_info": r"fehlende angaben|fehlende informationen|missing information|follow-up",
    "seek_help": r"beraten|beratung|mieterverband|anwalt|lawyer",
    "disclaimer": r"keine rechtsberatung|kein entscheid|not legal advice",
}
_DECISION_WORDS = r"\b(wird hiermit entschieden|ist rechtskräftig|urteil:|verfügung:|you are hereby)\b"


def companion_check(answer: str) -> dict:
    a = (answer or "").lower()
    present = {k: bool(re.search(p, a)) for k, p in _PATTERNS.items()}
    return {"completeness": round(sum(present.values()) / len(present), 3),
            "missing_sections": [k for k, v in present.items() if not v],
            "decision_language": bool(re.search(_DECISION_WORDS, a))}
