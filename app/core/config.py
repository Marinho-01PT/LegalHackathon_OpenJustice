"""Settings from the environment / .env. No Streamlit here, so the core can be reused (CLI, API, tests)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ojbench.cli import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    default_protocol: str     # OJ_PROTOCOL_ID: preselected protocol (built in the OpenJustice GUI)
    default_model: str        # OJ_MODEL: preselected model; empty = first Apertus model offered
    mock: bool                # offline fake API (automatic when no key is set)
    app_name: str
    legal_area: str = "Mietrecht"   # LEGAL_AREA: used to look for help nearby
    publicai_key: str = ""    # PUBLICAI_API_KEY: follow-up actions run on Apertus via Public AI
    publicai_model: str = ""  # PUBLICAI_MODEL: empty = largest Apertus model offered

    @property
    def cache_key(self) -> str:
        return f"{self.mock}|{self.base_url}|{self.api_key[-6:]}"


def load_settings() -> Settings:
    load_dotenv(str(ROOT / ".env"))
    key = os.environ.get("OJ_API_KEY", "").strip()
    return Settings(
        api_key=key,
        base_url=os.environ.get("OJ_BASE_URL", "https://api.openjustice.ai").strip(),
        default_protocol=os.environ.get("OJ_PROTOCOL_ID", "").strip(),
        default_model=os.environ.get("OJ_MODEL", "").strip(),
        mock=os.environ.get("APP_MOCK", "").strip() in ("1", "true", "yes") or not key,
        app_name=os.environ.get("APP_NAME", "ProtoLex").strip(),
        legal_area=os.environ.get("LEGAL_AREA", "Mietrecht").strip(),
        publicai_key=os.environ.get("PUBLICAI_API_KEY", "").strip(),
        publicai_model=os.environ.get("PUBLICAI_MODEL", "").strip(),
    )
