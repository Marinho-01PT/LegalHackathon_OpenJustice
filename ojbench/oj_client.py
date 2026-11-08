"""Thin HTTP client for the OpenJustice API (https://api.openjustice.ai/api/docs).

Endpoints used:
  GET  /reasoning-protocols?scope=all            list protocols
  GET  /reasoning-protocols/{id}                 Protocol Graph (nodes + edges)
  GET  /reasoning-protocol/v1/models             models a protocol can run on
  POST /reasoning-protocol/v1/responses          run a protocol node by node (baseline engine)
  GET  /reasoning-protocol/v1/responses/{id}/node_results/{nr}/trace   exact LLM calls per node
  GET  /agent/v1/models                          models of the agent endpoint
  POST /agent/v1/responses                       agent loop (plan-based + direct engines, judge)
  POST /file-library/citations/uploaded          upload law texts (multipart, vectorize=true)
  GET  /files                                    list own files
  POST /file-library/citations/pinpoints         verify verbatim quotes against a file (exact match)

Auth: `Authorization: Bearer $OJ_API_KEY`. Stdlib only.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


class OJError(RuntimeError):
    pass


class OJClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: int = 600):
        # verified: endpoints live directly under https://api.openjustice.ai (override with OJ_BASE_URL)
        self.base = (base_url or os.environ.get("OJ_BASE_URL", "https://api.openjustice.ai")).rstrip("/")
        self.key = api_key or os.environ.get("OJ_API_KEY", "")
        self.timeout = timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> tuple[dict, float]:
        req = urllib.request.Request(
            self.base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                     "User-Agent": "ojbench-hackathon/0.2"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise OJError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}") from None
        return data, time.perf_counter() - t0

    def get(self, path: str) -> dict:
        return self._req("GET", path)[0]

    def post(self, path: str, body: dict) -> tuple[dict, float]:
        return self._req("POST", path, body)

    # convenience
    def list_protocols(self, scope: str = "all") -> list[dict]:
        return self.get(f"/reasoning-protocols?scope={scope}")

    def protocol_graph(self, pid: str) -> dict:
        return self.get(f"/reasoning-protocols/{pid}")

    def models(self) -> dict:
        return {"protocol": [m["id"] for m in self.get("/reasoning-protocol/v1/models")["data"]],
                "agent": [m["id"] for m in self.get("/agent/v1/models")["data"]]}

    def run_protocol(self, body: dict) -> tuple[dict, float]:
        return self.post("/reasoning-protocol/v1/responses", body)

    def node_trace(self, resp_id: str, nr_id: str) -> dict:
        return self.get(f"/reasoning-protocol/v1/responses/{resp_id}/node_results/{nr_id}/trace")

    def agent(self, body: dict) -> tuple[dict, float]:
        return self.post("/agent/v1/responses", body)

    def files(self) -> list[dict]:
        return self.get("/files")

    def upload(self, path: str, strategy: str | None = "statute", metadata: dict | None = None) -> dict:
        """multipart/form-data upload, indexed for search (vectorize=true)."""
        import mimetypes
        import uuid
        from pathlib import Path
        f = Path(path)
        boundary = uuid.uuid4().hex
        parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{f.name}\"\r\n"
                 f"Content-Type: {mimetypes.guess_type(f.name)[0] or 'application/octet-stream'}\r\n\r\n".encode()
                 + f.read_bytes() + b"\r\n"]
        if metadata:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{json.dumps(metadata)}\r\n".encode())
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        q = "?vectorize=true" + (f"&enrichmentStrategy={strategy}" if strategy else "")
        req = urllib.request.Request(self.base + "/file-library/citations/uploaded" + q, method="POST", data=data,
                                     headers={"Authorization": f"Bearer {self.key}", "User-Agent": "ojbench-hackathon/0.3",
                                              "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise OJError(f"upload -> {e.code}: {e.read().decode(errors='replace')[:500]}") from None


def output_text(resp: dict) -> str:
    """Join all assistant message texts of a Responses-format object (like the SDK's output_text)."""
    parts = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
    return "\n".join(parts)


def usage_of(resp: dict) -> tuple[int, int]:
    u = resp.get("usage") or {}
    return u.get("input_tokens", 0), u.get("output_tokens", 0)
