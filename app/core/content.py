"""Content the legal team edits: FAQ (data/faq.json) and dev cases (data/cases/dev/*.json).
Test cases (data/cases/test) are never loaded by the app."""
from __future__ import annotations

import json

from ojbench.models import Case

from .config import DATA


def load_faq() -> list[dict]:
    f = DATA / "faq.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def load_dev_cases() -> list[Case]:
    return [Case.from_json(f) for f in sorted((DATA / "cases" / "dev").glob("*.json"))]
