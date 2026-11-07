"""Streamlit glue: cached settings/service/catalogue and the current selection from the sidebar."""
from __future__ import annotations

import streamlit as st

from app.core.config import Settings, load_settings
from app.core.service import OJService


@st.cache_resource(show_spinner=False)
def settings() -> Settings:
    return load_settings()


@st.cache_resource(show_spinner=False)
def _service(cache_key: str, mock: bool, api_key: str, base_url: str) -> OJService:
    return OJService.create(mock=mock, api_key=api_key, base_url=base_url)


def service() -> OJService:
    s = settings()
    return _service(s.cache_key, s.mock, s.api_key, s.base_url)


@st.cache_data(ttl=300, show_spinner=False)
def protocols(cache_key: str) -> list[dict]:
    return service().list_protocols()


@st.cache_data(ttl=300, show_spinner=False)
def models(cache_key: str) -> list[str]:
    return service().models()


def selection() -> tuple[str | None, str | None]:
    """(protocol_id, model) chosen in the sidebar."""
    return st.session_state.get("protocol_id"), st.session_state.get("model")
