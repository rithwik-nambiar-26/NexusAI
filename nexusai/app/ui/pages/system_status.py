"""System status page: what the backend reports about itself.

Everything on this page comes from the backend's own status endpoint.
Nothing is asserted here that the backend has not reported.
"""

from __future__ import annotations

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui import api_client
from nexusai.app.ui.components import (
    require_backend,
    show_api_error,
)
from nexusai.app.ui.config import API_BASE_URL


def render() -> None:
    """Render the System status page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("System status")
    st.caption(
        f"The state of the backend at `{API_BASE_URL}`, as reported by the "
        "backend itself."
    )

    if not require_backend():
        return

    st.divider()

    if st.button("Refresh", key="status_refresh"):
        try:
            st.session_state["status_system"] = api_client.system_status()
            st.session_state["status_tools"] = api_client.list_execution_tools()
        except api_client.ApiError as error:
            show_api_error(error)
            return

    system = st.session_state.get("status_system")
    tools = st.session_state.get("status_tools")

    if system is None:
        try:
            system = api_client.system_status()
            tools = api_client.list_execution_tools()
        except api_client.ApiError as error:
            show_api_error(error)
            return
        st.session_state["status_system"] = system
        st.session_state["status_tools"] = tools

    st.subheader("Application")
    columns = st.columns(3)
    columns[0].metric("App", system.get("app", "-"))
    columns[1].metric("Version", system.get("version", "-"))
    columns[2].metric("Environment", system.get("environment", "-"))

    st.subheader("Services")
    services = system.get("services") or []
    if services:
        st.dataframe(
            [
                {
                    "service": service.get("name"),
                    "available": service.get("available"),
                    "configured": service.get("configured"),
                    "detail": service.get("detail"),
                }
                for service in services
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Limits")
    limits = system.get("limits") or {}
    if limits:
        st.dataframe(
            [{"limit": key, "value": value} for key, value in limits.items()],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Registered execution capabilities")
    tool_list = (tools or {}).get("tools") or []
    if tool_list:
        st.dataframe(
            [
                {
                    "capability": tool.get("capability"),
                    "risk": tool.get("risk"),
                    "approval": tool.get("requires_approval"),
                    "permissions": ", ".join(tool.get("permissions") or []),
                    "timeout (s)": tool.get("timeout_seconds"),
                    "max attempts": tool.get("max_attempts"),
                }
                for tool in tool_list
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No capabilities are registered.")

    st.caption(
        "Only capabilities listed here can be executed. A plan that names "
        "anything else will have that task skipped rather than attempted."
    )
