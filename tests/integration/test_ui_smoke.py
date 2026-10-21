"""Streamlit UI smoke tests.

These tests actually execute the Streamlit app via ``AppTest`` so that a
rendering error in any page fails the suite. They are deterministic and
require no network, LLM, or running backend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "nexusai" / "app" / "ui" / "app.py"

pytest.importorskip("streamlit")
AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


@pytest.fixture
def app_test():
    """A fresh AppTest for the main UI entry point with navigation pre-set."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.session_state["nav_radio"] = "Overview"
    # Run once to initialize widgets with correct session state
    at.run()
    return at


def test_app_file_exists():
    assert APP_PATH.is_file(), f"Streamlit entry point missing: {APP_PATH}"


def test_app_renders_without_exception(app_test):
    at = app_test.run()
    assert not at.exception, f"Streamlit app raised: {at.exception}"


def test_app_shows_nexusai_branding(app_test):
    at = app_test.run()
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    )
    assert "NexusAI" in body


def test_app_has_navigation_for_every_page(app_test):
    at = app_test.run()
    # Get the options from the radio widget, not the label
    radio_widget = at.radio[0]
    options = radio_widget.options
    assert options, "expected a navigation radio widget with options"
    assert "Overview" in options
    for page in (
        "Task Automation",
        "Document Intelligence",
        "Data Intelligence",
        "Run History",
        "System status",
    ):
        assert page in options, f"navigation is missing the {page!r} page"


def test_overview_page_lists_all_six_objectives(app_test):
    at = app_test.run()
    # Collect all text content from various element types
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    )
    for objective in ("O1", "O2", "O3", "O4", "O5", "O6"):
        assert objective in body, f"overview page does not mention {objective}"


def test_overview_page_states_implemented_and_planned_work(app_test):
    """The UI must distinguish what is built from what is not yet built."""
    at = app_test.run()
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    )
    assert "Implemented today" in body
    assert "Day 2" in body and "Day 7" in body


def test_navigating_to_each_page_renders(app_test):
    """Every navigation target must render without raising."""
    radio_widget = app_test.run().radio[0]
    for label in radio_widget.options:
        at = app_test.run()
        at.radio[0].set_value(label).run()
        assert not at.exception, f"page {label!r} raised: {at.exception}"


def test_task_automation_page_does_not_fake_results(app_test):
    """The task page must not present fabricated workflow output."""
    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    assert not at.exception
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    )
    assert "Task Automation" in body
    # A run-history table may exist, but it must be empty, not populated
    # with invented runs.
    for table in at.dataframe:
        assert len(table.value) == 0, "run history must not be pre-populated with fake rows"


def test_system_status_page_does_not_claim_services_available(app_test):
    at = app_test.run()
    at.radio[0].set_value("System status").run()
    assert not at.exception
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    )
    assert "not configured" in body.lower() or "unavailable" in body.lower()


def test_document_intelligence_page_is_marked_not_implemented(app_test):
    at = app_test.run()
    at.radio[0].set_value("Document Intelligence").run()
    assert not at.exception
    body = " ".join(
        m.value for m in at.markdown
    ) + " " + " ".join(
        h.value for h in at.header
    ) + " " + " ".join(
        s.value for s in at.subheader
    ) + " " + " ".join(
        i.value for i in at.info
    )
    assert "Day 4" in body
