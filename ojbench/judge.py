"""Answer quality 1-5 (citation quality, factual accuracy, legal reasoning).

Priority: hand scores in scores/manual.csv > LLM judge. Use a DIFFERENT model than the one that
answered, and hand-score a sample to report judge-human agreement.
Note: RUBRIC paraphrases the three dimensions of the OpenJustice evaluation matrix; hand scores take precedence.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import Case, EngineResult
from .oj_client import OJClient, output_text

DIMS = ("citation_quality", "factual_accuracy", "legal_reasoning")

RUBRIC = """citation_quality: 1 = none or invented ... 5 = precise, correct pinpoint citations supporting each claim
factual_accuracy: 1 = misstates facts ... 5 = uses all relevant facts correctly and flags missing ones
legal_reasoning:  1 = conclusion without analysis ... 5 = complete, correctly ordered analysis incl. exceptions"""

SCHEMA = {"type": "object", "additionalProperties": False, "required": [*DIMS, "rationale"],
          "properties": {**{d: {"type": "integer"} for d in DIMS}, "rationale": {"type": "string"}}}


def llm_judge(client: OJClient, model: str, case: Case, r: EngineResult) -> dict:
    prompt = (f"RUBRIC:\n{RUBRIC}\n\nCASE:\n{case.prompt_block()}\n\nREFERENCE ANALYSIS (ground truth):\n"
              f"{case.reference_analysis}\n\nANSWER TO GRADE:\n{r.answer}\n\nFollow-up questions asked: {r.follow_up_questions}")
    resp, _ = client.agent({"model": model, "tools": [], "input": prompt,
                            "instructions": "You grade legal answers strictly against the rubric and the reference analysis. Scores are integers 1-5.",
                            "text": {"format": {"type": "json_schema", "name": "grade", "strict": True, "schema": SCHEMA}}})
    return json.loads(output_text(resp))


def manual_scores(path: str | Path = "scores/manual.csv") -> dict[tuple[str, str], dict]:
    """CSV header: engine,case_id,citation_quality,factual_accuracy,legal_reasoning"""
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as f:
        return {(r["engine"], r["case_id"]): {d: int(r[d]) for d in DIMS} for r in csv.DictReader(f)}
