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
    parts += [s.value for s in at.success]
    parts += [w.value for w in at.warning]
    parts += [e.value for e in at.error]
    parts += [c.value for c in at.caption]
    parts += [t.value for t in at.title]
    # Widget labels are visible text too.
    parts += [b.label for b in at.button]
    for radio in at.radio:
        parts.append(str(radio.label))
        parts += [str(option) for option in radio.options]
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


# ---------------------------------------------------------------------------
# The intent-confirmation flow
# ---------------------------------------------------------------------------


UNCERTAIN_CLASSIFICATION = {
    "result": {
        "predicted_intent": "document_summarisation",
        "confidence": 0.24,
        "status": "clarification_required",
        "clarification_question": "I'm not sure I understand.",
        "all_scores": {
            "document_summarisation": 0.24,
            "document_transformation": 0.16,
            "document_question_answering": 0.158,
            "research": 0.14,
            "destructive_operation": 0.038,
        },
    }
}


def _intent_radio(at):
    """Return the intent-confirmation radio, or fail if it is not rendered."""
    for radio in at.radio:
        if radio.label == "Which intent did you mean?":
            return radio
    raise AssertionError(
        "the intent confirmation radio was not rendered: "
        f"{[r.label for r in at.radio]}"
    )


def test_uncertain_classification_offers_ranked_candidates(app_test, monkeypatch):
    """A low-confidence classification must offer the ranked candidates."""
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: UNCERTAIN_CLASSIFICATION
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value(
        "Summarise the uploaded meeting notes and identify the important decisions."
    ).run()

    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    body = _body(at)
    # The confirmation step is offered.
    assert "Confirm the intent" in body
    # The candidates are listed with their scores.
    assert "document summarisation" in body
    assert "0.240" in body
    # The refusal paths are labelled as such.
    assert "refusal path" in body
    # And the user is asked to choose.
    assert "Which intent did you mean?" in body

    # The candidates are ranked, most likely first, and each carries its
    # score.
    radio = _intent_radio(at)
    assert radio.options[0] == "document summarisation (0.240)"
    assert radio.options[1] == "document transformation (0.160)"
    assert radio.options[-1] == "destructive operation (0.038) (refusal path)"


def test_confirming_an_intent_is_recorded_and_used(app_test, monkeypatch):
    """A confirmed intent is stored and reported as the one being used."""
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: UNCERTAIN_CLASSIFICATION
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value(
        "Summarise the uploaded meeting notes and identify the important decisions."
    ).run()

    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    # Choose the summarisation intent explicitly.
    _intent_radio(at).set_value("document summarisation (0.240)").run()
    confirm_button = next(b for b in at.button if b.label == "Confirm this intent")
    at = confirm_button.click().run()

    assert at.session_state["task_confirmed_intent"] == "document_summarisation"
    body = _body(at)
    assert "Intent confirmed by you" in body
    # The plan can now be generated.
    assert "Generate plan" in body


def test_a_confident_classification_does_not_offer_the_confirmation_step(
    app_test, monkeypatch
):
    """A confident classification is planned directly."""
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.91,
            "status": "confident",
            "all_scores": {"document_summarisation": 0.91, "research": 0.04},
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value("Summarise the meeting notes.").run()

    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    body = _body(at)
    assert "Confirm the intent" not in body
    assert "Generate plan" in body


def test_a_new_request_clears_a_previous_confirmation(app_test, monkeypatch):
    """Confirming an intent must not carry over to the next request."""
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: UNCERTAIN_CLASSIFICATION
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value(
        "Summarise the uploaded meeting notes and identify the important decisions."
    ).run()

    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()
    _intent_radio(at).set_value("document summarisation (0.240)").run()
    confirm_button = next(b for b in at.button if b.label == "Confirm this intent")
    at = confirm_button.click().run()
    assert at.session_state["task_confirmed_intent"] == "document_summarisation"

    # A new request clears the confirmation.
    at.text_area[0].set_value("Read the product manual and list the requirements.").run()
    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    assert "task_confirmed_intent" not in at.session_state
    assert "Intent confirmed by you" not in _body(at)


# ---------------------------------------------------------------------------
# The Reminders page
# ---------------------------------------------------------------------------


def test_reminders_page_states_the_delivery_limitation(app_test, monkeypatch):
    """The page must say that a reminder needs NexusAI to be running."""
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client, "list_reminders", lambda *a, **k: {"reminders": [], "count": 0}
    )

    at = app_test.run()
    at.radio[0].set_value("Reminders").run()

    body = _body(at)
    # The limitation is stated, not implied.
    assert "only while NexusAI is running" in body
    assert "missed" in body
    # And the fact that no operating-system job is registered is stated.
    assert "Windows" in body


def test_reminders_page_lists_stored_reminders(app_test, monkeypatch):
    """A stored reminder is shown with its due time and status."""
    from nexusai.app.ui import api_client

    monkeypatch.setattr(
        api_client,
        "list_reminders",
        lambda *a, **k: {
            "reminders": [
                {
                    "id": 1,
                    "message": "Team standup",
                    "due_at": "2026-10-23T03:30:00+00:00",
                    "local_due_at": "2026-10-23T09:00:00+05:30",
                    "timezone": "Asia/Kolkata",
                    "status": "pending",
                }
            ],
            "count": 1,
        },
    )

    at = app_test.run()
    at.radio[0].set_value("Reminders").run()

    body = _body(at)
    assert "Team standup" in body
    assert "pending" in body
    assert "2026-10-23T09:00:00+05:30" in body


# ---------------------------------------------------------------------------
# The summary, the source document and the stale clarification warning
# ---------------------------------------------------------------------------


def test_a_confirmed_intent_clears_the_stale_clarification_warning(
    app_test, monkeypatch
):
    """The clarification question must not persist after the user answers it."""
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.24,
            "status": "clarification_required",
            "clarification_question": "I'm not sure I understand.",
            "all_scores": {
                "document_summarisation": 0.24,
                "document_transformation": 0.16,
            },
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: {"documents": []})

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value("Summarise the uploaded meeting notes.").run()

    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    # Before the confirmation, the question is still outstanding.
    assert "I'm not sure I understand." in _body(at)

    _intent_radio(at).set_value("document summarisation (0.240)").run()
    confirm_button = next(b for b in at.button if b.label == "Confirm this intent")
    at = confirm_button.click().run()

    # After the confirmation, it has been answered and is not repeated.
    body = _body(at)
    assert "Intent confirmed by you" in body
    assert "I'm not sure I understand." not in body


def test_the_plan_shows_the_selected_document(app_test, monkeypatch):
    """The plan must show which document it is about."""
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.9,
            "status": "confident",
            "all_scores": {"document_summarisation": 0.9},
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(
        api_client,
        "list_documents",
        lambda *a, **k: {
            "documents": [
                {"name": "meeting_notes.md", "document_id": "doc_meeting"},
            ]
        },
    )

    plan = {
        "plan_id": "plan_1",
        "intent": "document_summarisation",
        "plan_status": "ready",
        "requires_approval": False,
        "source": "explicit",
        "source_documents": ["doc_meeting"],
        "tasks": [],
        "dependencies": [],
        "execution_order": [],
        "parallel_levels": [],
        "missing_information": [],
        "unsupported_operations": [],
        "validation_errors": [],
        "clarification_required": False,
        "clarification_question": None,
    }
    monkeypatch.setattr(
        api_client, "create_plan", lambda *a, **k: {"plan": plan}
    )

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value("Summarise the meeting notes.").run()
    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    generate_button = next(b for b in at.button if b.label == "Generate plan")
    at = generate_button.click().run()

    body = _body(at)
    assert "Source document" in body
    assert "doc_meeting" in body

def test_a_stale_plan_cannot_be_executed_after_the_document_changes(
    app_test, monkeypatch
):
    """Changing the document must not leave the old plan executable.

    The defect was that a plan built for one document could still be
    executed after the user selected a different one, so the workflow ran
    against a document the user had not chosen.
    """
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.9,
            "status": "confident",
            "all_scores": {"document_summarisation": 0.9},
        }
    }
    documents = {
        "documents": [
            {"name": "meeting_notes.md", "document_id": "doc_meeting"},
            {"name": "product_manual.md", "document_id": "doc_manual"},
        ]
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(api_client, "list_documents", lambda *a, **k: documents)

    plan = {
        "plan_id": "plan_1",
        "intent": "document_summarisation",
        "plan_status": "ready",
        "requires_approval": False,
        "source": "explicit",
        "source_documents": ["doc_meeting"],
        "tasks": [],
        "dependencies": [],
        "execution_order": [],
        "parallel_levels": [],
        "missing_information": [],
        "unsupported_operations": [],
        "validation_errors": [],
        "clarification_required": False,
        "clarification_question": None,
    }
    monkeypatch.setattr(api_client, "create_plan", lambda *a, **k: {"plan": plan})
    executed = []
    monkeypatch.setattr(
        api_client,
        "execute_plan",
        lambda p, **k: executed.append(p) or {"report": {"status": "completed", "task_results": []}},
    )

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value("Summarise the meeting notes.").run()
    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()

    # Choose the meeting notes and build a plan for it.
    options = at.selectbox[0].options
    at.selectbox[0].set_value(next(o for o in options if "meeting_notes" in o)).run()
    at = next(b for b in at.button if b.label == "Generate plan").click().run()
    assert at.session_state["task_plan_context"]["documents"] == ["doc_meeting"]

    # Now change the selection. The plan is stale and must not run.
    options = at.selectbox[0].options
    at.selectbox[0].set_value(next(o for o in options if "product_manual" in o)).run()

    body = _body(at)
    assert "out of date" in body
    assert "Execute plan" not in [b.label for b in at.button]
    assert executed == []


def test_a_stale_plan_cannot_be_executed_after_the_request_changes(
    app_test, monkeypatch
):
    """Changing the request text must not leave the old plan executable."""
    from nexusai.app.ui import api_client

    classification = {
        "result": {
            "predicted_intent": "document_summarisation",
            "confidence": 0.9,
            "status": "confident",
            "all_scores": {"document_summarisation": 0.9},
        }
    }
    monkeypatch.setattr(
        api_client, "classify_intent", lambda *a, **k: classification
    )
    monkeypatch.setattr(
        api_client,
        "list_documents",
        lambda *a, **k: {
            "documents": [{"name": "meeting_notes.md", "document_id": "doc_meeting"}]
        },
    )

    plan = {
        "plan_id": "plan_1",
        "intent": "document_summarisation",
        "plan_status": "ready",
        "requires_approval": False,
        "source": "explicit",
        "source_documents": ["doc_meeting"],
        "tasks": [],
        "dependencies": [],
        "execution_order": [],
        "parallel_levels": [],
        "missing_information": [],
        "unsupported_operations": [],
        "validation_errors": [],
        "clarification_required": False,
        "clarification_question": None,
    }
    monkeypatch.setattr(api_client, "create_plan", lambda *a, **k: {"plan": plan})
    executed = []
    monkeypatch.setattr(
        api_client,
        "execute_plan",
        lambda p, **k: executed.append(p) or {"report": {"status": "completed", "task_results": []}},
    )

    at = app_test.run()
    at.radio[0].set_value("Task Automation").run()
    at.text_area[0].set_value("Summarise the meeting notes.").run()
    classify_button = next(b for b in at.button if b.label == "Classify and plan")
    at = classify_button.click().run()
    options = at.selectbox[0].options
    at.selectbox[0].set_value(next(o for o in options if "meeting_notes" in o)).run()
    at = next(b for b in at.button if b.label == "Generate plan").click().run()

    # Change the request text without re-classifying.
    at.text_area[0].set_value("Something entirely different.").run()

    body = _body(at)
    assert "out of date" in body
    assert executed == []
