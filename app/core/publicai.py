"""Apertus directly via Public AI (https://platform.publicai.co), used for follow-up actions (e.g. the e-mail).
Builds on ojbench.publicai. Model: PUBLICAI_MODEL, else picked from /models (largest Apertus)."""
from __future__ import annotations

import re
from functools import lru_cache

from ojbench.publicai import PublicAI


def _size(model_id: str) -> int:
    m = re.search(r"(\d+)\s*b\b", model_id.lower())
    return int(m.group(1)) if m else 0


@lru_cache(maxsize=4)
def client(api_key: str, model: str) -> PublicAI:
    c = PublicAI(model=model or "x", api_key=api_key)
    if not model:
        ids = c.list_models()
        apertus = [i for i in ids if "apertus" in i.lower()]
        if not apertus:
            raise RuntimeError(f"Kein Apertus-Modell bei Public AI gefunden. Verfügbar: {', '.join(ids[:10])}")
        c.model = max(apertus, key=lambda i: (_size(i), "instruct" in i.lower()))
    return c
