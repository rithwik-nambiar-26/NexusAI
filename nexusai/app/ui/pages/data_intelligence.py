"""Data Intelligence page: profile a CSV file and aggregate over it.

The analysis is an independent, explicitly user-triggered workflow. It
calls the registered ``data.analyse`` capability directly, so it uses the
same registry, the same input and output validation and the same
filesystem policy as every other capability. It requires no task plan,
and so cannot be affected by a plan left over from another page.
"""

from __future__ import annotations

from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover
    st = None  # type: ignore[assignment]

from nexusai.app.ui import api_client
from nexusai.app.ui.components import (
    require_backend,
    show_api_error,
)


def render() -> None:
    """Render the Data Intelligence page."""
    if st is None:
        raise RuntimeError("streamlit is required to render the UI")

    st.title("Data Intelligence")
    st.caption(
        "Profile a CSV file and aggregate over a column you choose. Every figure "
        "comes from the file itself; nothing is predicted or inferred."
    )

    if not require_backend():
        return

    st.divider()

    # ------------------------------------------------------------------
    # Choose the file
    # ------------------------------------------------------------------
    st.subheader("1 · Choose a dataset")

    uploaded = st.file_uploader(
        "Upload a CSV file",
        type=["csv", "tsv"],
        key="data_upload",
    )
    st.caption(
        "The file must sit inside the backend's allowed document roots "
        "(data, docs, experiments)."
    )
    path = st.text_input(
        "Or use a file already in the project",
        value="data/sample/sales_2026.csv",
        key="data_path",
    )

    if uploaded is not None:
        from nexusai.app.config import REPO_ROOT
        from nexusai.app.ui.config import UPLOAD_DIR

        upload_dir = Path(UPLOAD_DIR)
        if not upload_dir.is_absolute():
            upload_dir = REPO_ROOT / upload_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / Path(uploaded.name).name
        target.write_bytes(uploaded.getvalue())
        path = str(target)
        st.caption(f"Using the uploaded file: `{target}`")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    st.divider()
    st.subheader("2 · Analyse")

    group_by = st.text_input(
        "Group by column (optional)",
        placeholder="e.g. region",
        key="data_group_by",
    )
    measure = st.text_input(
        "Measure to sum (optional)",
        placeholder="e.g. revenue",
        key="data_measure",
    )

    if st.button("Analyse dataset", type="primary", key="data_analyse"):
        if not path.strip():
            st.error("Please choose a dataset.")
        else:
            with st.spinner("Analysing..."):
                try:
                    response = api_client.analyse_csv(
                        path=path.strip(),
                        group_by=group_by.strip() or None,
                        measure=measure.strip() or None,
                    )
                except api_client.ApiError as error:
                    show_api_error(error)
                    return
            st.session_state["data_analysis_output"] = response.get("output") or {}

    output = st.session_state.get("data_analysis_output")
    if not output:
        st.info("Analyse a dataset to see its profile and totals.")
        return

    st.markdown("**Dataset**")
    columns = st.columns(3)
    columns[0].metric("Rows", output.get("rows", 0))
    columns[1].metric("Columns", output.get("columns", 0))
    columns[2].metric("Source", output.get("source", "-"))

    st.markdown("**Columns**")
    st.write(", ".join(output.get("column_names") or []))

    profiles = output.get("profiles") or []
    if profiles:
        st.markdown("**Column profile**")
        st.dataframe(
            [
                {
                    "column": profile.get("name"),
                    "type": profile.get("dtype"),
                    "missing": profile.get("missing"),
                    "missing %": profile.get("missing_percent"),
                    "unique": profile.get("unique"),
                    "example": profile.get("example"),
                }
                for profile in profiles
            ],
            use_container_width=True,
            hide_index=True,
        )

    descriptives = output.get("numeric_descriptives") or {}
    if descriptives:
        st.markdown("**Descriptive statistics**")
        rows = []
        for column, stats in descriptives.items():
            row = {"column": column}
            row.update({key: f"{value:,.2f}" for key, value in stats.items()})
            rows.append(row)
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if output.get("aggregation"):
        st.markdown(f"**Aggregation** — {output['aggregation']}")

    totals = output.get("grouped_totals") or []
    if totals:
        st.markdown("**Results**")
        st.dataframe(totals, use_container_width=True, hide_index=True)

    for note in output.get("notes") or []:
        st.info(note)

    st.caption(
        f"Every figure above is computed from `{output.get('source')}` by the "
        "registered `data.analyse` capability."
    )
