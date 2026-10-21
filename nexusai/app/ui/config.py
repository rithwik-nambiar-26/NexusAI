"""Streamlit configuration: API base URL and branding."""

from __future__ import annotations

import os

try:  # pragma: no cover - optional at import time
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]


API_BASE_URL = os.getenv("NEXUSAI_API_URL", "http://127.0.0.1:8000")
APP_NAME = "NexusAI"
APP_VERSION = "0.1.0"
TAGLINE = "AI-Powered Personal Task Automation"

#: Timeout for a single backend call, in seconds.
REQUEST_TIMEOUT_SECONDS = float(os.getenv("NEXUSAI_API_TIMEOUT", "30"))

#: Where uploaded files are written before the backend ingests them.
#: This must sit inside the backend's allowed document roots so the same
#: PathPolicy governs an upload as any other read.
UPLOAD_DIR = os.getenv("NEXUSAI_UPLOAD_DIR", "./data/uploads")

PAGES = [
    ("Overview", "overview"),
    ("Task Automation", "task_automation"),
    ("Document Intelligence", "document_intelligence"),
    ("Data Intelligence", "data_intelligence"),
    ("Run History", "run_history"),
    ("System status", "system_status"),
]

NAV_ICONS = {
    "Overview": "🏠",
    "Task Automation": "⚙️",
    "Document Intelligence": "📄",
    "Data Intelligence": "📊",
    "Run History": "🕒",
    "System status": "🛡️",
}


def page_config() -> None:
    """Configure the Streamlit page once per session."""
    if st is None:
        return
    st.set_page_config(
        page_title=f"{APP_NAME} — {TAGLINE}",
        page_icon="🔗",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def branding_css() -> None:
    """Inject minimal, clean branding CSS (no fake metrics or charts)."""
    if st is None:
        return
    st.markdown(
        """
        <style>
        .nexus-hero {
            padding: 1.5rem 1rem;
            background: #0e1117;
            border-radius: 0.5rem;
            margin-bottom: 1.5rem;
        }
        .nexus-title {
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.01em;
            margin: 0;
        }
        .nexus-subtitle {
            color: #94a3b8;
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }
        .nexus-section {
            margin-top: 1.5rem;
        }
        .status-badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 1rem;
            font-size: 0.75rem;
            font-weight: 600;
            border: 1px solid transparent;
        }
        .badge-available { color: #166534; background: #dcfce7; border-color: #86efac; }
        .badge-unavailable { color: #9ca3af; background: #f3f4f6; border-color: #d1d5db; }
        .badge-pending { color: #92400e; background: #fef3c7; border-color: #fcd34d; }
        .nexus-footer {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
            color: #6b7280;
            font-size: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def header() -> None:
    """Render the top branding bar."""
    if st is None:
        return
    with st.container(border=True):
        st.markdown(
            f"""
            <div class="nexus-hero">
                <h1 class="nexus-title">{APP_NAME}</h1>
                <p class="nexus-subtitle">{TAGLINE} &middot; v{APP_VERSION} &middot; local-first &middot; Python-only</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
