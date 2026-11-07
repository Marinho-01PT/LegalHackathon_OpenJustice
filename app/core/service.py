"""OpenJustice access for the app. Builds on ojbench (client, mock, protocol mapping, direct instruction).

Arm A, with protocol:   POST /reasoning-protocol/v1/responses  (protocol built in the OpenJustice GUI)
Arm B, without:         POST /agent/v1/responses               (same model, standard instruction, no tools)
"""
from __future__ import annotations

import copy
import json
import time

from ojbench.engines.direct import STANDARD_INSTRUCTION
from ojbench.engines.openjustice import MISSING_FACT_REPLY
from ojbench.mock import MockOJClient
from ojbench.models import Case, Protocol
from ojbench.oj_client import OJClient, output_text, usage_of
from ojbench.protocol import map_graph

from .config import DATA
from .models import Question, RunResult, Step

_BOOL = {"true": "Ja", "false": "Nein", "yes": "Ja", "no": "Nein", "ja": "Ja", "nein": "Nein"}


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Ja" if v else "Nein"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, indent=1)
    return str(v).strip()


def _chip(v: str) -> str:
    """Short outputs become a value chip; long ones stay in the detail only."""
    s = " ".join(v.split())
    return _BOOL.get(s.lower(), s) if 0 < len(s) <= 40 else ""


def friendly_error(exc) -> str:
    msg = str(exc)
    if "-> 401" in msg or "-> 403" in msg:
        return "Die API lehnt den Schlüssel ab. Prüfen Sie OJ_API_KEY in der Datei .env."
    if "-> 404" in msg:
        return "Endpunkt oder Prüfschema nicht gefunden. Prüfen Sie OJ_BASE_URL (mit oder ohne /api) und die Protokoll-ID."
    if "-> 524" in msg or "-> 504" in msg:
        return "Zeitüberschreitung: OpenJustice hat zu lange nicht geantwortet. Versuchen Sie es erneut."
    if "-> 429" in msg:
        return "Tageslimit erreicht oder zu viele gleichzeitige Anfragen. Warten Sie kurz und versuchen Sie es erneut."
    if "urlopen error" in msg or "timed out" in msg:
        return "OpenJustice ist nicht erreichbar. Prüfen Sie die Internetverbindung."
    return msg[:400] or "Unbekannter Fehler."


def build_prompt(facts: str, question: str, jurisdiction: str = "CH", legal_date: str = "") -> str:
    return Case(id="app", facts=facts, question=question, protocol_id="",
                jurisdiction=jurisdiction, legal_date=legal_date).prompt_block()


class OJService:
    def __init__(self, client, mock: bool = False):
        self.client, self.mock = client, mock
        self._graphs: dict[str, Protocol | None] = {}
        self._bases: dict[str, tuple[RunResult, float]] = {}   # response id -> (state before it, start time)

    @classmethod
    def create(cls, mock: bool, api_key: str = "", base_url: str = "") -> "OJService":
        if mock:
            return cls(MockOJClient(DATA / "protocols"), mock=True)
        return cls(OJClient(base_url=base_url or None, api_key=api_key), mock=False)

    # ---------------------------------------------------------------- catalogue
    def list_protocols(self) -> list[dict]:
        def norm(data):
            items = data.get("data", data.get("items", [])) if isinstance(data, dict) else data
            return [{"id": p.get("id"), "name": p.get("name") or p.get("title") or p.get("id")} for p in items or []]
        if self.mock:
            return norm(self.client.list_protocols())
        return norm(self.client.list_protocols("own")) or norm(self.client.list_protocols("all"))

    def models(self) -> list[str]:
        """Models offered by both endpoints, so both arms run on the same model (fair comparison)."""
        m = self.client.models()
        both = [x for x in m["protocol"] if x in set(m["agent"])]
        return both or m["protocol"]

    def protocol(self, pid: str) -> Protocol | None:
        if pid not in self._graphs:
            try:
                self._graphs[pid] = map_graph(self.client.protocol_graph(pid))
            except Exception:
                self._graphs[pid] = None     # labels fall back to node ids
        return self._graphs[pid]

    # ---------------------------------------------------------------- arm A: with protocol
    # Runs start with background: true and are polled (GET /responses/{id}): no gateway timeout on long
    # protocols (Cloudflare cuts synchronous calls after ~100 s, HTTP 524), and the UI can show each
    # node result as soon as it exists.
    POLL_SECONDS = 1.5
    MAX_WAIT = 900

    def start(self, pid: str, model: str, prompt: str) -> RunResult:
        body = {"reasoning_protocol_id": pid, "model": model, "input": prompt, "background": True}
        return self._post(pid, body, RunResult("protocol"))

    def answer_questions(self, pid: str, model: str, prior: RunResult, answers: dict[str, str]) -> RunResult:
        text = "\n".join(f"{q.label}: {answers.get(q.id) or 'unbekannt'}" for q in prior.pending)
        return self._resume(pid, model, prior, text)

    def skip_questions(self, pid: str, model: str, prior: RunResult) -> RunResult:
        return self._resume(pid, model, prior, MISSING_FACT_REPLY)

    def _resume(self, pid, model, prior, text) -> RunResult:
        body = {"previous_response_id": prior.response_id, "model": model, "input": text, "background": True}
        return self._post(pid, body, prior)

    def _post(self, pid: str, body: dict, base: RunResult) -> RunResult:
        t0 = time.perf_counter()
        try:
            resp, _ = self.client.run_protocol(body)
        except Exception as exc:
            res = copy.deepcopy(base)
            res.status, res.error = "failed", friendly_error(exc)
            return res
        self._bases[resp.get("id")] = (base, t0)
        return self._apply(pid, base, resp, time.perf_counter() - t0)

    def poll(self, pid: str, res: RunResult) -> RunResult:
        """Current state of a background run (output so far)."""
        base, t0 = self._bases.get(res.response_id, (RunResult("protocol"), time.perf_counter()))
        try:
            resp = self.client.get(f"/reasoning-protocol/v1/responses/{res.response_id}")
        except Exception as exc:
            out = copy.deepcopy(res)
            out.status, out.error = "failed", friendly_error(exc)
            return out
        return self._apply(pid, base, resp, time.perf_counter() - t0, count_request=False)

    def wait(self, pid: str, res: RunResult, on_update=None) -> RunResult:
        """Poll until the run leaves in_progress; on_update(res) after every poll (live UI)."""
        t_end = time.monotonic() + self.MAX_WAIT
        while res.status == "in_progress":
            if time.monotonic() > t_end:
                res.status, res.error = "failed", "Der Lauf dauert länger als 15 Minuten und wurde nicht weiter abgefragt."
                break
            time.sleep(self.POLL_SECONDS)
            res = self.poll(pid, res)
            if on_update:
                on_update(res)
        return res

    def run_protocol(self, pid: str, model: str, prompt: str, on_update=None) -> RunResult:
        return self.wait(pid, self.start(pid, model, prompt), on_update)

    def run_protocol_unattended(self, pid: str, model: str, prompt: str, max_resumes: int = 3) -> RunResult:
        """For batch comparisons: missing facts are answered with 'not stated' (same as the ojbench baseline)."""
        res = self.run_protocol(pid, model, prompt)
        for _ in range(max_resumes):
            if res.status != "awaiting_input":
                break
            res = self.wait(pid, self.skip_questions(pid, model, res))
        return res

    def node_trace(self, response_id: str, nr_id: str) -> dict:
        """The exact LLM calls one node made (system prompts left out by the API)."""
        return self.client.node_trace(response_id, nr_id)

    def _apply(self, pid: str, base: RunResult, resp: dict, secs: float, count_request: bool = True) -> RunResult:
        """base (state before this Flow Response) + this Flow Response's output -> new RunResult."""
        res = copy.deepcopy(base)
        res.pending = []
        tin, tout = usage_of(resp)
        res.usage["input_tokens"] += tin
        res.usage["output_tokens"] += tout
        res.usage["seconds"] = base.usage.get("seconds", 0.0) + secs
        res.usage["requests"] = base.usage.get("requests", 0) + 1
        res.response_id = resp.get("id")
        res.execution_id = resp.get("execution_id") or res.execution_id
        graph = self.protocol(pid)

        for item in resp.get("output", []):
            t = item.get("type")
            if t == "node_result" and item.get("status", "completed") == "completed":
                nid, ntype = item.get("node_id", ""), item.get("node_type", "")
                node = graph.nodes.get(nid) if graph else None
                label = (node.label if node else "") or nid
                out = _text(item.get("output"))
                if ntype == "outcome":
                    res.outcome_id, res.outcome_label = nid, label
                    res.steps.append(Step(nid, "outcome", label, "", out, "", item.get("id", ""), res.response_id))
                elif ntype in ("reasoning", "fact"):
                    res.steps.append(Step(nid, ntype, label, _chip(out), out, node.question if node else "",
                                          item.get("id", ""), res.response_id))
            elif t == "fact":
                pred = _text(item.get("prediction"))
                res.steps.append(Step(item.get("node_id", ""), "fact", item.get("label") or item.get("node_id", ""),
                                      _chip(pred) or pred[:40], item.get("rationale") or ""))
            elif t == "pending_input":
                for fd in item.get("fact_definitions", []):
                    res.pending.append(Question(fd.get("id", ""), fd.get("label", ""),
                                                fd.get("question") or fd.get("instructions") or fd.get("label", ""),
                                                fd.get("dataType") or fd.get("data_type") or "text", bool(fd.get("required"))))
        status = resp.get("status")
        text = output_text(resp).strip()
        if text and status != "incomplete":          # incomplete: the message only repeats the pending questions
            res.answer = f"{base.answer}\n\n{text}".strip()
        if status == "in_progress":
            res.status = "in_progress"
        elif status in ("failed", "cancelled"):
            res.status = "failed"
            res.error = friendly_error((resp.get("error") or {}).get("message") or resp.get("error") or status)
        elif status == "incomplete" and (resp.get("incomplete_details") or {}).get("reason") == "awaiting_input":
            res.status = "awaiting_input"
        else:
            res.status = "completed"
        return res

    # ---------------------------------------------------------------- arm B: without protocol
    def run_direct(self, model: str, prompt: str) -> RunResult:
        res = RunResult("direct")
        try:
            resp, secs = self.client.agent({"model": model, "instructions": STANDARD_INSTRUCTION,
                                            "input": prompt, "tools": []})
        except Exception as exc:
            res.status, res.error = "failed", friendly_error(exc)
            return res
        tin, tout = usage_of(resp)
        res.usage.update(input_tokens=tin, output_tokens=tout, seconds=secs, requests=1)
        res.response_id, res.answer = resp.get("id"), output_text(resp).strip()
        return res
