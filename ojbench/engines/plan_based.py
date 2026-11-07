"""Our engine: read the whole protocol, distill it into a plan, run it in ONE agent request.

1. distill_plan(): the plan STRUCTURE comes from the graph by code (no LLM) -> no branch,
   condition, exception or source can be lost. Sub-reasoning children come before their parent,
   switches become explicit IF/OTHERWISE rules with the real conditions.
2. The agent (POST /agent/v1/responses) gets case + plan and must return JSON with a typed
   value for every node it worked on. We later re-evaluate the switches on those values in code
   (fidelity.py) and check that the agent's claimed outcome is the one the protocol dictates.
"""
from __future__ import annotations

import json
import re

from ..models import Case, EngineResult, Protocol, TraceStep
from ..oj_client import OJClient, output_text, usage_of
from ..protocol import render_condition
from ..companion import FRAME_INSTRUCTION, SCHEMA_PROPS, render


# ------------------------------------------------------------------ distillation
def _value_hint(n) -> str:
    if n.type == "fact":
        return "facts"
    if n.enum_values:
        return "one of " + " | ".join(n.enum_values)
    return n.data_type or "text"


def distill_plan(p: Protocol) -> str:
    lines: list[str] = []
    done: set[str] = set()

    def step(n, pad: str, num: str) -> None:
        done.add(n.id)
        if n.type == "fact":
            lines.append(f"{pad}{num} [node_id={n.id}] FACTS – {n.label}. Establish from the case file:")
            for fd in n.fact_definitions:
                req = "required" if fd.get("required") else "optional"
                lines.append(f"{pad}    - {fd['label']} ({fd.get('dataType')}, {req}): {fd.get('question') or fd.get('instructions')}")
            lines.append(f"{pad}    If a required fact is not in the case file: value 'unknown' + add a follow-up question.")
        else:
            lines.append(f"{pad}{num} [node_id={n.id}] {n.type.upper()} – {n.label}: {n.question} {n.instructions}".rstrip())
            lines.append(f"{pad}    value: {_value_hint(n)}")
            for s in n.sources:
                lines.append(f"{pad}    source: {s}")

    def walk(nid: str | None, pad: str, prefix: str) -> None:
        i = 0
        while nid:
            n = p.nodes[nid]
            if n.id in done and n.type != "outcome":
                lines.append(f"{pad}(then continue as in [node_id={n.id}] above)")
                return
            if n.type in ("fact", "reasoning"):
                i += 1
                subs = p.subs(n.id)
                for j, c in enumerate(subs, 1):
                    step(c, pad, f"{prefix}{i}.{j}")
                if subs:
                    lines.append(f"{pad}    -> the next step must combine ALL considerations {prefix}{i}.1–{prefix}{i}.{len(subs)}")
                step(n, pad, f"{prefix}{i}.")
            elif n.type == "switch":
                i += 1
                done.add(n.id)
                lines.append(f"{pad}{prefix}{i}. [switch={n.id}] DECISION – {n.label}. Take exactly ONE branch:")
                for k, e in enumerate(p.branches(n.id), 1):
                    lines.append(f"{pad}   {render_condition(e)}:")
                    walk(e.dst, pad + "      ", f"{prefix}{i}.{k}.")
                return
            elif n.type == "outcome":
                done.add(n.id)
                lines.append(f"{pad}=> OUTCOME [outcome={n.id}] {n.label}. {n.instructions} {n.template}".rstrip())
                return
            nxt = p.next(n.id)
            nid = nxt.id if nxt else None

    walk(p.start().id, "", "")
    return "\n".join(lines)


def plan_coverage(p: Protocol, plan: str) -> dict:
    ids = set(re.findall(r"\[(?:node_id|switch|outcome)=([^\]]+)\]", plan))
    required = {n.id for n in p.nodes.values() if n.type != "start"}
    missing = sorted(required - ids)
    return {"coverage": round(1 - len(missing) / max(len(required), 1), 3), "missing": missing}


# ------------------------------------------------------------------ execution
INSTRUCTIONS = """You are a careful Swiss legal analyst. Solve the case strictly by following the PLAN.
- Work through the steps in order. Do every step on the path you take, incl. every consideration and listed source.
- At a DECISION take exactly one branch, determined by the values you assigned. Never work on branches not taken.
- Give every step a value in the requested type ('unknown' if the case file does not say).
- Cite precise sources (article, paragraph, decision). Prefer the sources listed in the plan.
- Missing facts: do not guess, add a follow-up question.
{law}
{frame}

PLAN:
{plan}"""

LAW_HINT = """- The attached law files are authoritative. Read them (read_file / file_search) before citing.
  For every step add 1-2 VERBATIM quotes (20-600 characters, copied exactly, no ellipsis) with the file_id."""

_STEP = {"node_id": {"type": "string"}, "value": {"type": "string"}, "finding": {"type": "string"},
         "sources": {"type": "array", "items": {"type": "string"}},
         "quotes": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                               "required": ["file_id", "quote"],
                                               "properties": {"file_id": {"type": "string"}, "quote": {"type": "string"}}}}}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["steps", "outcome_node_id", "follow_up_questions", *SCHEMA_PROPS],
    "properties": {
        "steps": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": list(_STEP), "properties": _STEP}},
        "outcome_node_id": {"type": ["string", "null"]},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        **SCHEMA_PROPS,
    },
}

TOOL_ITEMS = {"tool_call", "file_search_call", "web_search_call"}


class PlanBasedEngine:
    """plan_based: closed book. With law_files -> plan_based_rag: the uploaded law texts are attached and the
    agent may read/search them; its verbatim quotes are later verified via /file-library/citations/pinpoints."""

    def __init__(self, client: OJClient, model: str, law_files: list[dict] | None = None, max_tool_calls: int = 12):
        self.client, self.model = client, model
        self.law_files = law_files or []
        self.name = "plan_based_rag" if self.law_files else "plan_based"
        self.tools = [{"type": "read_file"}, {"type": "file_search", "vector_store_ids": [], "max_num_results": 8}] if self.law_files else []
        self.max_tool_calls = max_tool_calls
        self._plans: dict[str, str] = {}

    def plan_for(self, p: Protocol) -> str:
        key = f"{p.id}@{p.version}"
        if key not in self._plans:
            self._plans[key] = distill_plan(p)
        return self._plans[key]

    def _input(self, case: Case):
        if not self.law_files:
            return case.prompt_block()
        files = "\n".join(f"- file_id {f['id']}: {f.get('name', '')}" for f in self.law_files)
        return [{"role": "user", "content": [{"type": "input_text", "text": f"{case.prompt_block()}\n\nLAW FILES:\n{files}"},
                                             *[{"type": "input_file", "file_id": f["id"]} for f in self.law_files]]}]

    def run(self, protocol: Protocol, case: Case) -> EngineResult:
        instr = INSTRUCTIONS.format(plan=self.plan_for(protocol), law=LAW_HINT if self.law_files else "", frame=FRAME_INSTRUCTION)
        body = {"model": self.model, "instructions": instr, "input": self._input(case), "tools": self.tools,
                "text": {"format": {"type": "json_schema", "name": "protocol_run", "strict": True, "schema": SCHEMA}}}
        if self.tools:
            body["max_tool_calls"] = self.max_tool_calls
        usage: dict = {}
        try:
            resp, secs = self.client.agent(body)
            tin, tout = usage_of(resp)
            tool_calls = sum(1 for it in resp.get("output", []) if it.get("type") in TOOL_ITEMS)
            usage = {"llm_calls": 1 + tool_calls, "llm_calls_exact": False, "tool_calls": tool_calls,
                     "input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout, "seconds": round(secs, 2)}
            if resp.get("status") != "completed":
                raise RuntimeError(f"agent status {resp.get('status')}: {resp.get('incomplete_details') or resp.get('error')}")
            d = json.loads(output_text(resp))
            trace = [TraceStep(s["node_id"], None if s["value"] == "unknown" else s["value"], s["finding"], s["sources"])
                     for s in d["steps"]]
            quotes = [q for s in d["steps"] for q in s.get("quotes", [])]
            questions = d.get("follow_up_questions", [])
            return EngineResult(self.name, case.id, self.model, render(d, questions), trace, d.get("outcome_node_id"),
                                questions, usage, [resp.get("id", "")], quotes=quotes)
        except Exception as exc:
            return EngineResult(self.name, case.id, self.model, "", [], None, [], usage, [], repr(exc))
