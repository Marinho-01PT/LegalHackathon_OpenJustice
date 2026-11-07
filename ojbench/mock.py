"""Offline stand-in for the OpenJustice API: same response shapes, no network, no credits.
Lets the whole pipeline (and CI) run before the real key works. Answers are meaningless."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .protocol import evaluate_switch, map_graph


class MockOJClient:
    def __init__(self, protocols_dir: str | Path = "data/protocols"):
        self.raw = {}
        for f in Path(protocols_dir).glob("*.raw.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            self.raw[d["id"]] = d
        self.n = 0

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}_{self.n:04d}"

    def list_protocols(self, scope="all"):
        return [{"id": k, "name": v["name"]} for k, v in self.raw.items()]

    def protocol_graph(self, pid):
        return self.raw[pid]

    def models(self):
        return {"protocol": ["mock"], "agent": ["mock"]}

    def node_trace(self, resp_id, nr_id):
        return {"call_count": 1}

    def files(self):
        return []

    def upload(self, path, strategy="statute", metadata=None):
        return {"id": self._id("file"), "name": Path(path).name}

    def post(self, path, body):
        if path.endswith("/pinpoints"):   # pretend every second quote is found
            return {"results": [{"found": True, "url": "mock://quote", "startChar": 0, "endChar": 1, "page": None,
                                 "textRevision": 1} if i % 2 == 0 else {"found": False, "reason": "not_found"}
                                for i, _ in enumerate(body["items"])]}, 0.0
        raise NotImplementedError(path)

    @staticmethod
    def _val(n):   # deterministic fake value: first boolean node 'false', others 'true'
        return "false" if n.id in ("formular",) else "true"

    def _walk(self, p):
        values, out = {}, []
        nid = p.start().id
        while True:
            n = p.nodes[nid]
            if n.type in ("fact", "reasoning"):
                for c in p.subs(n.id) + [n]:
                    v = None if c.type == "fact" else self._val(c)
                    if c.id == "formgueltig":
                        v = values.get("formular", "true")
                    values[c.id] = v
                    out.append((c, v))
            if n.type == "switch":
                e, _ = evaluate_switch(p, n.id, values)
                nid = e.dst
                continue
            if n.type == "outcome":
                return out, n
            nid = p.next(n.id).id

    def run_protocol(self, body):
        p = map_graph(self.raw[body["reasoning_protocol_id"]])
        steps, outcome = self._walk(p)
        items = [{"id": self._id("nr"), "type": "node_result", "status": "completed", "node_id": n.id,
                  "node_type": n.type, "output": v or "facts extracted", "usage": {"input_tokens": 500, "output_tokens": 50}}
                 for n, v in steps]
        items.append({"id": self._id("nr"), "type": "node_result", "status": "completed", "node_id": outcome.id,
                      "node_type": "outcome", "output": "mock outcome"})
        items.append({"type": "message", "content": [{"type": "output_text", "text": f"Mock: {outcome.label}"}]})
        k = len(items) - 1
        return ({"id": self._id("resp"), "status": "completed", "output": items,
                 "usage": {"input_tokens": 500 * k, "output_tokens": 50 * k}}, 0.0)

    def agent(self, body):
        fmt = (body.get("text") or {}).get("format", {})
        if fmt.get("name") == "protocol_run":
            pid = None
            for k, v in self.raw.items():
                if all(f"[node_id={n['id']}]" in body["instructions"] for n in v["nodes"] if n["type"] in ("reasoning",)):
                    pid = k
            p = map_graph(self.raw[pid])
            steps, outcome = self._walk(p)
            rag = bool(body.get("tools"))
            text = json.dumps({"steps": [{"node_id": n.id, "value": v or "unknown", "finding": "mock", "sources": ["Art. 269d OR"],
                                          "quotes": [{"file_id": "file_mock", "quote": "Der Vermieter kann den Mietzins jederzeit erhöhen."}] if rag else []}
                                         for n, v in steps],
                               "outcome_node_id": outcome.id, "follow_up_questions": ["Datum des Zugangs?"],
                               "assessment": f"Mock: {outcome.label} (Art. 269d OR, Art. 999z OR)", "confidence": "mittel",
                               "confidence_reason": "mock", "deadlines": [{"what": "Anfechtung", "until": "30 Tage", "legal_basis": "Art. 270b OR", "if_missed": "verwirkt"}],
                               "options": ["A"], "next_steps": ["Schlichtungsbehörde"], "seek_help": "Mieterverband"})
            tin = len(body["instructions"]) // 4
        elif fmt.get("name") == "grade":
            text, tin = json.dumps({"citation_quality": 3, "factual_accuracy": 3, "legal_reasoning": 3, "rationale": "mock"}), 400
        else:
            text, tin = "## Einschätzung\nMock (Art. 269d OR)\n## Nächste Schritte\n- x", 300
        return ({"id": self._id("resp"), "status": "completed",
                 "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
                 "usage": {"input_tokens": tin, "output_tokens": len(text) // 4}}, 0.0)
