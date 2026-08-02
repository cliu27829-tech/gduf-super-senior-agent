"""Configuration access without mutating process-global secrets."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


load_dotenv()

DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_CHAT_MODEL = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")


def get_setting(name: str, default: Any = "") -> Any:
    value = os.getenv(name)
    if value not in (None, ""):
        return value
    try:
        import streamlit as st

        return st.secrets[name] if name in st.secrets else default
    except Exception:
        return default


def get_deepseek_api_key() -> str:
    return str(get_setting("DEEPSEEK_API_KEY", ""))


def get_admin_token() -> str:
    return str(get_setting("GDUF_ADMIN_TOKEN", ""))
