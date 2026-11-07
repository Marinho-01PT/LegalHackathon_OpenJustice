"""Cited articles: do they exist? (local Fedlex export in data/law/*.txt, no LLM) + link to Fedlex."""
from __future__ import annotations

import re
from functools import lru_cache

from ojbench.citations import build_index, extract

from .config import DATA

FEDLEX = {
    "OR": "https://www.fedlex.admin.ch/eli/cc/27/317_321_377/de",
    "ZGB": "https://www.fedlex.admin.ch/eli/cc/24/233_245_233/de",
    "ZPO": "https://www.fedlex.admin.ch/eli/cc/2010/262/de",
    "BV": "https://www.fedlex.admin.ch/eli/cc/1999/404/de",
    "SchKG": "https://www.fedlex.admin.ch/eli/cc/11/529_488_529/de",
}


@lru_cache(maxsize=1)
def _index() -> dict[str, set[str]]:
    return build_index(DATA / "law")


def _num(art: str) -> int:
    return int(re.match(r"\d+", art).group())


def _url(code: str, art: str) -> str | None:
    base = next((v for k, v in FEDLEX.items() if k.upper() == code), None)
    if not base:
        return None
    m = re.match(r"(\d+)([a-z]?)", art)
    return f"{base}#art_{m[1]}" + (f"_{m[2]}" if m[2] else "")


def check_sources(text: str) -> list[dict]:
    """[{ref, status: ok|missing|unchecked, url}] in order of first appearance."""
    idx = _index()
    ranges = {k: (min(map(_num, v)), max(map(_num, v))) for k, v in idx.items() if v}
    seen, out = set(), []
    for c in extract(text):
        key = (c["code"], c["art"])
        if key in seen:
            continue
        seen.add(key)
        r = ranges.get(c["code"])
        if r and r[0] <= _num(c["art"]) <= r[1]:
            status = "ok" if c["art"] in idx[c["code"]] else "missing"
        else:
            status = "unchecked"
        out.append({"ref": f"Art. {c['art']} {c['code']}", "status": status, "url": _url(c["code"], c["art"])})
    return out


def valid_rate(text: str) -> float | None:
    s = check_sources(text)
    checked = [x for x in s if x["status"] != "unchecked"]
    return sum(x["status"] == "ok" for x in checked) / len(checked) if checked else None
