"""Direct access to Apertus via Public AI (https://platform.publicai.co), for prompt experiments only.

Not used by the benchmark (that runs everything through OpenJustice with the same model id
`publicai-apertus-70b`). Needs PUBLICAI_API_KEY in .env. Public AI requires a User-Agent header.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("PUBLICAI_BASE_URL", "https://api.publicai.co/v1")


class PublicAI:
    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.key = api_key or os.environ.get("PUBLICAI_API_KEY", "")
        self.model = model or os.environ.get("PUBLICAI_MODEL", "")   # see list_models(), take the 70B like OpenJustice
        if not self.key:
            raise SystemExit("PUBLICAI_API_KEY missing in .env")

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(BASE + path, method=method,
                                     data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                                              "User-Agent": "ojbench-hackathon/0.3"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:400]}") from None

    def list_models(self) -> list[str]:
        return [m["id"] for m in self._req("GET", "/models").get("data", [])]

    def chat(self, system: str, user: str, temperature: float = 0.0) -> dict:
        t0 = time.perf_counter()
        d = self._req("POST", "/chat/completions", {"model": self.model, "temperature": temperature,
                                                    "messages": [{"role": "system", "content": system},
                                                                 {"role": "user", "content": user}]})
        u = d.get("usage") or {}
        return {"text": d["choices"][0]["message"]["content"], "seconds": round(time.perf_counter() - t0, 2),
                "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens")}
