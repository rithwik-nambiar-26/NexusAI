"""Streamlit application entry point.

Run with:

    streamlit run nexusai/app/ui/app.py
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

# Make `streamlit run nexusai/app/ui/app.py` work from a source checkout
# without requiring the package to be installed first.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    raise SystemExit("streamlit is not installed") from None

from nexusai.app.ui.config import (
    APP_NAME,
    APP_VERSION,
    PAGES,
    TAGLINE,
    branding_css,
    header,
)
from nexusai.app.ui.pages import (
    data_intelligence,
    document_intelligence,
    overview,
    run_history,
    system_status,
    task_automation,
)

PAGE_MODULES: dict[str, Callable[[], None]] = {
    "overview": overview.render,
    "task_automation": task_automation.render,
    "document_intelligence": document_intelligence.render,
    "data_intelligence": data_intelligence.render,
    "run_history": run_history.render,
    "system_status": system_status.render,
}


def main() -> None:
    st.set_page_config(
        page_title=f"{APP_NAME} — {TAGLINE}",
        page_icon="🔗",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    branding_css()
    header()

    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(f"v{APP_VERSION} &middot; local-first")
        st.divider()
        st.subheader("Navigate")
        labels = [label for label, _ in PAGES]
        # Use a key so session state can pre-populate the selection
        choice = st.radio(
            "Go to",
            labels,
            index=0,
            label_visibility="collapsed",
            key="nav_radio",
        )
        st.divider()
        st.markdown(
            "Status: **engineering foundation (Day 1)** &middot; AI agent subsystems in Days 2–7"
        )

    # Handle test framework quirk: widget may be initialized with label as value
    # before our session_state takes effect. Fall back to first page.
    if choice not in labels:
        choice = labels[0]
    page_key = dict(PAGES)[choice]
    page_module = PAGE_MODULES[page_key]
    page_module()

    st.divider()
    st.markdown(
        f"""
        <div style="color:#6b7280; font-size:0.75rem;">
        {APP_NAME} v{APP_VERSION} &middot; MSc Data Science project &middot;
        College Second Review: 23–25 October 2026
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
