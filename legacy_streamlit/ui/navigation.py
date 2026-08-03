"""Navigation helpers that also work when a page is tested in isolation."""

from __future__ import annotations

import streamlit as st


def safe_page_link(page: str, label: str) -> None:
    try:
        st.page_link(page, label=label)
    except KeyError:
        # Streamlit's isolated AppTest runner has no multipage registry. The
        # production runtime does, so keep a non-clickable label in tests only.
        st.caption(label)
