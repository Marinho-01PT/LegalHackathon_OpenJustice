"""Baseline: the existing OpenJustice engine (one LLM step per node), via POST /reasoning-protocol/v1/responses."""
from __future__ import annotations

from ..models import Case, EngineResult, Protocol, TraceStep
from ..oj_client import OJClient, output_text, usage_of

MISSING_FACT_REPLY = ("This information is not stated in the case file. Continue with what is known "
                      "and state clearly which facts are missing.")


class OpenJusticeEngine:
    name = "openjustice_node_by_node"

    def __init__(self, client: OJClient, model: str, max_resumes: int = 3, exact_calls: bool = False):
        self.client, self.model = client, model
        self.max_resumes = max_resumes
        self.exact_calls = exact_calls      # True: read every Node Trace for the exact number of LLM calls

    def run(self, protocol: Protocol, case: Case) -> EngineResult:
        trace, questions, answers, ids = [], [], [], []
        tin = tout = 0
        secs = 0.0
        outcome = None
        node_results = 0
        llm_calls = 0
        body = {"reasoning_protocol_id": protocol.id, "model": self.model, "input": case.prompt_block()}
        try:
            for _ in range(self.max_resumes + 1):
                resp, dt = self.client.run_protocol(body)
                secs += dt
                ids.append(resp["id"])
                a, b = usage_of(resp)
                tin, tout = tin + a, tout + b
                answers.append(output_text(resp))
                for item in resp.get("output", []):
                    t = item.get("type")
                    if t == "node_result" and item.get("status") == "completed":
                        node_results += 1
                        if self.exact_calls:
                            llm_calls += self.client.node_trace(resp["id"], item["id"]).get("call_count", 0)
                        if item.get("node_type") == "outcome":
                            outcome = item["node_id"]
                        else:
                            trace.append(TraceStep(item["node_id"], item.get("output"), item.get("output") or ""))
                    elif t == "fact":
                        # facts carry typed predictions; keep them as values for switch evaluation
                        trace.append(TraceStep(item["node_id"], item.get("prediction"),
                                               f"{item.get('label')}: {item.get('prediction')} ({item.get('rationale', '')})"))
                    elif t == "pending_input":
                        questions += [fd.get("label", "") + ": " + (fd.get("instructions") or "") for fd in item.get("fact_definitions", [])]
                if resp.get("status") == "failed":
                    raise RuntimeError(resp.get("error"))
                if resp.get("status") == "incomplete" and (resp.get("incomplete_details") or {}).get("reason") == "awaiting_input":
                    body = {"previous_response_id": resp["id"], "model": self.model, "input": MISSING_FACT_REPLY}
                    continue
                break
            # merge fact values into one value per node (single fact definition -> plain value)
            merged: dict[str, TraceStep] = {}
            for t in trace:
                if t.node_id in merged and merged[t.node_id].value is None:
                    merged[t.node_id].value = t.value
                merged.setdefault(t.node_id, t)
            return EngineResult(self.name, case.id, self.model, "\n".join(x for x in answers if x).strip(),
                                list(merged.values()), outcome, questions,
                                {"llm_calls": llm_calls if self.exact_calls else node_results,
                                 "llm_calls_exact": self.exact_calls, "input_tokens": tin, "output_tokens": tout,
                                 "total_tokens": tin + tout, "seconds": round(secs, 2), "api_requests": len(ids)}, ids)
        except Exception as exc:
            return EngineResult(self.name, case.id, self.model, "", trace, outcome, questions,
                                {"input_tokens": tin, "output_tokens": tout, "total_tokens": tin + tout,
                                 "seconds": round(secs, 2)}, ids, repr(exc))
