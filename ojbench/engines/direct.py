"""Control condition: the same model, the case and a standard instruction, NO protocol."""
from __future__ import annotations

import re

from ..companion import FRAME_INSTRUCTION
from ..models import Case, EngineResult, Protocol
from ..oj_client import OJClient, output_text, usage_of

STANDARD_INSTRUCTION = ("You are a careful Swiss legal analyst. Answer the question for the case below. "
                        "Cite precise sources (article, paragraph, decision). If facts are missing, do not guess: "
                        "list them under the heading 'Fehlende Angaben'.\n" + FRAME_INSTRUCTION)


class DirectEngine:
    name = "direct"

    def __init__(self, client: OJClient, model: str):
        self.client, self.model = client, model

    def run(self, protocol: Protocol, case: Case) -> EngineResult:
        try:
            resp, secs = self.client.agent({"model": self.model, "instructions": STANDARD_INSTRUCTION,
                                            "input": case.prompt_block(), "tools": []})
            tin, tout = usage_of(resp)
            text = output_text(resp)
            questions = []
            m = re.search(r"Fehlende Angaben\s*\n(.*?)(?:\n#+ |\Z)", text, re.S)
            if m:
                questions = [q.strip("-• ").strip() for q in m.group(1).splitlines() if q.strip().startswith(("-", "•"))]
            return EngineResult(self.name, case.id, self.model, text.strip(), [], None, questions,
                                {"llm_calls": 1, "llm_calls_exact": False, "input_tokens": tin, "output_tokens": tout,
                                 "total_tokens": tin + tout, "seconds": round(secs, 2)}, [resp.get("id", "")])
        except Exception as exc:
            return EngineResult(self.name, case.id, self.model, "", [], None, [], {}, [], repr(exc))
