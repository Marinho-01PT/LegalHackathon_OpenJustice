"""Citation checks without an LLM.

1. exists_rate:  do the cited articles exist? Checked against the law texts in data/law/*.txt
                 (e.g. OR Art. 253–274g, exported from Fedlex). Article level; unknown codes = unchecked.
2. verified_quote_rate: are verbatim quotes really in the uploaded law files? Checked server-side with
                 OpenJustice POST /file-library/citations/pinpoints (exact match, never fuzzy).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CODES = r"OR|ZGB|ZPO|VMWG|BV|SchKG|DSG"
CITE_RE = re.compile(rf"Art\.?\s*(\d+[a-z]?)(?:\s*Abs\.?\s*(\d+))?(?:\s*lit\.?\s*([a-z]))?\s*({CODES})\b")
# Fedlex copies glue footnote numbers to headings ("Art. 259i102", "Art. 274–274g113") -> strip them
HEAD_RE = re.compile(r"^\s*Art\.?\s*(\d+)([a-z]?)(\d*)(?=\b|[–-])", re.M)


def _headings(text: str) -> set[str]:
    out = set()
    for num, letter, tail in HEAD_RE.findall(text):
        if not letter and tail == "" and len(num) > 4:      # "Art. 26984" = Art. 269 + footnote 84
            num = num[:3]
        out.add(num + letter)
    return out


def build_index(law_dir: str | Path = "data/law") -> dict[str, set[str]]:
    """data/law/OR.txt -> {"OR": {"253", "269d", ...}}. File stem = law code."""
    idx: dict[str, set[str]] = {}
    for f in Path(law_dir).glob("*.txt"):
        idx[f.stem.upper()] = _headings(f.read_text(encoding="utf-8", errors="replace"))
    return idx


def extract(text: str) -> list[dict]:
    return [{"art": m[0], "abs": m[1] or None, "lit": m[2] or None, "code": m[3].upper(),
             "ref": " ".join(x for x in [f"Art. {m[0]}", f"Abs. {m[1]}" if m[1] else "", f"lit. {m[2]}" if m[2] else "", m[3]] if x)}
            for m in CITE_RE.findall(text or "")]


def _num(art: str) -> int:
    return int(re.match(r"\d+", art).group())


def exists_check(text: str, index: dict[str, set[str]]) -> dict:
    """Only articles inside the covered range of a law file are checked (e.g. OR.txt with only Art. 253-274g:
    a citation of Art. 41 OR stays unchecked instead of being counted as non-existent)."""
    cites = extract(text)
    ranges = {k: (min(map(_num, v)), max(map(_num, v))) for k, v in index.items() if v}
    checked = [c for c in cites if c["code"] in ranges and ranges[c["code"]][0] <= _num(c["art"]) <= ranges[c["code"]][1]]
    bad = [c["ref"] for c in checked if c["art"] not in index[c["code"]]]
    return {"n_citations": len(cites), "n_checked": len(checked),
            "exists_rate": round(1 - len(bad) / len(checked), 3) if checked else None,
            "nonexistent": sorted(set(bad))}


def verify_quotes(client, quotes: list[dict]) -> dict:
    """quotes: [{"file_id": ..., "quote": ...}] -> share found exactly once in the file."""
    items = [{"fileId": q["file_id"], "quote": q["quote"]} for q in quotes
             if q.get("file_id") and 20 <= len(q.get("quote", "")) <= 600 and "…" not in q["quote"] and "..." not in q["quote"]]
    if not items:
        return {"n_quotes": len(quotes), "verified_quote_rate": None, "not_verified": []}
    res, _ = client.post("/file-library/citations/pinpoints", {"items": items[:200]})
    results = res.get("results", [])
    ok = [r for r in results if r.get("found")]
    return {"n_quotes": len(items), "verified_quote_rate": round(len(ok) / len(results), 3) if results else None,
            "not_verified": [i["quote"][:80] for i, r in zip(items, results) if not r.get("found")],
            "links": [r["url"] for r in ok]}


def law_files(path: str | Path = "data/law/files.json") -> list[dict]:
    """Uploaded law files: [{"id": ..., "name": ..., "code": "OR"}] (written by `ojbench upload`)."""
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
