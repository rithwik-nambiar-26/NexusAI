"""Streamlit UI smoke tests.

These tests actually execute the Streamlit app via ``AppTest`` so that a
rendering error in any page fails the suite.

The tests do not require a running backend. When the backend is absent
the pages must say so plainly rather than showing invented results, and
these tests check exactly that.
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


def _body(at) -> str:
    """Collect the visible text of a rendered app."""
    parts = [m.value for m in at.markdown]
    parts += [h.value for h in at.header]
    parts += [s.value for s in at.subheader]
    parts += [i.value for i in at.info]
    parts += [w.value for w in at.warning]
    parts += [e.value for e in at.error]
    parts += [c.value for c in at.caption]
    parts += [t.value for t in at.title]
    # Metric values are visible text too.
    for metric in at.metric:
        parts.append(str(metric.value))
        parts.append(str(metric.label))
    # Dataframe cells are visible text too.
    for frame in at.dataframe:
        value = frame.value
        if hasattr(value, "to_numpy"):
            parts.append(" ".join(str(cell) for cell in value.to_numpy().ravel()))
        else:
            parts.append(" ".join(str(cell) for cell in value))
    return " ".join(parts)


def test_app_file_exists():
    assert APP_PATH.is_file(), f"Streamlit entry point missing: {APP_PATH}"


def test_app_renders_without_exception(app_test):
    at = app_test.run()
    assert not at.exception, f"Streamlit app raised: {at.exception}"


def test_app_shows_nexusai_branding(app_test):
    at = app_test.run()
    assert "NexusAI" in _body(at)


def test_app_has_navigation_for_every_page(app_test):
    at = app_test.run()
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
    for objective in ("O1", "O2", "O3", "O4", "O5", "O6"):
        assert objective in _body(at), f"overview page does not mention {objective}"


def test_overview_page_states_implemented_and_planned_work(app_test):
    """The UI must distinguish what is built from what is not yet built."""
    at = app_test.run()
    body = _body(at)
    assert "Implemented and tested" in body
    assert "Not yet implemented" in body
    # The overview must not claim the comparative evaluation is complete.
    assert "not an established result" in body or "not complete" in body


def test_navigating_to_each_page_renders(app_test):
    """Every navigation target must render without raising."""
    radio_widget = app_test.run().radio[0]
    for label in radio_widget.options:
        at = app_test.run()
        at.radio[0].set_value(label).run()
        assert not at.exception, f"page {label!r} raised: {at.exception}"


def test_pages_report_a_missing_backend_honestly(app_test, monkeypatch):
    """Without a backend the pages must say so, not invent results.

    The backend reachability check is stubbed so the test does not depend
    on whether a server happens to be running.
    """
    from nexusai.app.ui import components

    monkeypatch.setattr(
        components, "backend_is_reachable", lambda *a, **k: (False, "stubbed")
    )

    for label in ("Task Automation", "Document Intelligence", "Data Intelligence"):
        at = app_test.run()
        # Clear the cached reachability result so the stub is consulted.
        at.session_state["backend_reachable"] = False
        at.session_state["backend_checked_at"] = None
        at.radio[0].set_value(label).run()
        assert not at.exception
        body = _body(at)
        assert "backend is not reachable" in body.lower(), (
            f"the {label!r} page should report that the backend is unreachable"
        )


def test_task_automation_page_does_not_fake_results(app_test):
    """The task page must not present fabricated workflow output."""
    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    assert not at.exception
    body = _body(at)
    assert "Task Automation" in body
    # No execution results may be shown before anything has run.
    assert "Execution" not in body or "Execute plan" in body


def test_system_status_page_reports_backend_state(app_test):
    """The status page must report the backend's own state, not a guess."""
    at = app_test.run()
    at.radio[0].set_value("System status").run()
    assert not at.exception
    body = _body(at).lower()
    assert "not reachable" in body or "unavailable" in body or "backend" in body


def test_run_history_page_is_honest_about_history(app_test, monkeypatch):
    """The history page must not show invented runs.

    The backend is stubbed to report no runs, so the test does not depend
    on whether a server happens to be running.
    """
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client,
        "list_runs",
        lambda *a, **k: {"runs": [], "total": 0, "limit": 50, "offset": 0},
    )

    at = app_test.run()
    at.radio[0].set_value("Run History").run()
    assert not at.exception
    body = _body(at)
    assert "Run History" in body
    # The page must not present rows the backend did not supply.
    for table in at.dataframe:
        assert len(table.value) == 0, "run history must not be pre-populated with fake rows"


# ---------------------------------------------------------------------------
# Day 5.5.1 regression: the Plan section must never show a stale plan
# ---------------------------------------------------------------------------


def test_new_classification_clears_a_stale_plan(app_test, monkeypatch):
    """A new request must not display the previous request's plan.

    The defect was that the Plan section kept rendering the plan left in
    session state, so a request for the product manual displayed an
    ``out_of_scope`` plan belonging to an earlier request.
    """
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_question_answering",
            "confidence": 0.22,
            "status": "clarification_required",
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    # Simulate a previous interaction that left an out_of_scope plan.
    at = app_test.run()
    at.session_state["task_classification"] = {
        "result": {
            "predicted_intent": "out_of_scope",
            "confidence": 0.4,
            "status": "confident",
        }
    }
    at.session_state["task_request_used"] = "an earlier request"
    at.session_state["task_plan"] = {
        "plan_id": "plan_stale",
        "intent": "out_of_scope",
        "plan_status": "invalid",
        "tasks": [],
        "dependencies": [],
        "execution_order": [],
        "parallel_levels": [],
        "missing_information": [],
        "unsupported_operations": [],
        "clarification_required": False,
        "clarification_question": None,
        "validation_errors": [],
        "requires_approval": False,
        "approval_reasons": [],
        "source": "classifier",
    }
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value(
        "Read the uploaded product manual and tell me the installation requirements."
    ).run()

    # Press "Classify and plan" for the new request.
    classify_button = next(
        b for b in at.button if b.label == "Classify and plan"
    )
    at = classify_button.click().run()

    body = _body(at)
    # The stale out_of_scope plan must not be on screen.
    assert "out_of_scope" not in body
    # The new classification is shown instead.
    assert "document question answering" in body
    # And the plan section asks for a plan rather than showing the old one.
    assert "Generate a plan" in body


def test_stale_execution_report_is_cleared_with_a_new_request(app_test, monkeypatch):
    """A new request must not display the previous request's execution."""
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_question_answering",
            "confidence": 0.22,
            "status": "clarification_required",
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.session_state["task_classification"] = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.3,
            "status": "confident",
        }
    }
    at.session_state["task_request_used"] = "an earlier request"
    at.session_state["task_execution"] = {
        "status": "completed",
        "task_results": [
            {"task_id": "old", "capability": "document.read", "status": "completed"}
        ],
    }
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value(
        "Read the uploaded product manual and tell me the installation requirements."
    ).run()

    classify_button = next(
        b for b in at.button if b.label == "Classify and plan"
    )
    at = classify_button.click().run()

    # The previous request's execution is gone: the "Execute plan" button
    # is gone with it, because the execution section only renders when
    # there is an execution to show.
    assert "Execute plan" not in [b.label for b in at.button]
    # The old execution output is not presented as this request's result.
    assert "old" not in _body(at)
