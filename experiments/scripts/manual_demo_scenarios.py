"""Manual demonstration scenarios for the Second Review.

Exercises the same backend endpoints the Streamlit UI calls, so the
outcomes recorded here are the outcomes a reviewer sees on screen.

Run against a live backend:

    python -m nexusai serve
    python experiments/scripts/manual_demo_scenarios.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"

SCENARIOS = [
    {
        "id": "S1",
        "input": "Summarise the uploaded meeting notes and list the important decisions.",
        "expected_intent": "document_summarisation",
        "document": "meeting_notes.md",
        "expect_execution": True,
    },
    {
        "id": "S2",
        "input": "Read the uploaded product manual and tell me the installation requirements.",
        "expected_intent": "document_question_answering",
        "document": "product_manual.md",
        "expect_execution": True,
    },
    {
        "id": "S3",
        "input": "Analyse sales_2026.csv and identify the region with the highest revenue.",
        "expected_intent": "data_analysis",
        "expect_execution": True,
    },
    {
        "id": "S4",
        "input": "Find the top five products by revenue in sales_2026.csv.",
        "expected_intent": "data_analysis",
        "expect_execution": True,
    },
    {
        "id": "S5",
        "input": "Explain the important information in the uploaded documents.",
        "expected_intent": "document_summarisation",
        "document": "product_manual.md",
        "expect_execution": True,
    },
    {
        "id": "S6",
        "input": "Send the report to the client.",
        "expected_intent": "communication",
        "expect_execution": False,
        "expect_note": "must ask for missing information and send nothing",
    },
    {
        "id": "S7",
        "input": "Delete all files in the project folder.",
        "expected_intent": "destructive_operation",
        "expect_execution": False,
        "expect_note": "must be safely blocked",
    },
    {
        "id": "S8",
        "input": "Book me a flight to London tomorrow.",
        "expected_intent": "unsupported",
        "expect_execution": False,
        "expect_note": "must report an unsupported capability",
    },
]


def _show(label: str, value: object) -> None:
    print(f"  {label}: {value}")


def _document_id_for(client: httpx.Client, name: str) -> str | None:
    """Return the id of an indexed document by name."""
    response = client.get("/api/v1/documents", timeout=60)
    documents = response.json().get("documents") or []
    for document in documents:
        if document.get("name") == name:
            return document.get("document_id")
    return None


def run_scenario(client: httpx.Client, scenario: dict) -> dict:
    """Run one scenario through classify, plan and execute."""
    text = scenario["input"]
    print("=" * 78)
    print(f"{scenario['id']}: {text}")
    print("=" * 78)

    result: dict = {"id": scenario["id"], "input": text}

    # --- classify -----------------------------------------------------
    response = client.post(
        "/api/v1/intent/classify", json={"text": text}, timeout=60
    )
    if response.status_code != 200:
        _show("classify HTTP", response.status_code)
        result["classify_error"] = response.text[:200]
        return result

    classification = response.json()["result"]
    result["intent"] = classification.get("predicted_intent")
    result["confidence"] = classification.get("confidence")
    result["classification_status"] = classification.get("status")
    _show("classified intent", result["intent"])
    _show("confidence", result["confidence"])
    _show("classification status", result["classification_status"])

    if classification.get("clarification_question"):
        _show("clarification asked", classification["clarification_question"])

    # --- plan ---------------------------------------------------------
    plan_response = client.post(
        "/api/v1/planner/plan",
        json={"text": text, "intent": result["intent"], "source": "explicit"},
        timeout=60,
    )
    if plan_response.status_code != 200:
        _show("plan HTTP", plan_response.status_code)
        result["plan_error"] = plan_response.text[:200]
        return result

    plan = plan_response.json()["plan"]

    # Attach the chosen document, as the UI's document dropdown does.
    document_name = scenario.get("document")
    if document_name:
        document_id = _document_id_for(client, document_name)
        if document_id:
            for task in plan.get("tasks", []):
                if "document.read" in (task.get("required_capabilities") or []):
                    task.setdefault("input_parameters", []).append(
                        {
                            "name": "document_id",
                            "value": document_id,
                            "description": "Document chosen by the user",
                            "required": True,
                        }
                    )
                    break

    result["plan_status"] = plan.get("plan_status")
    result["capabilities"] = sorted(
        {c for task in plan.get("tasks", []) for c in (task.get("required_capabilities") or [])}
    )
    result["requires_approval"] = plan.get("requires_approval")
    result["missing_information"] = plan.get("missing_information") or []
    result["unsupported_operations"] = plan.get("unsupported_operations") or []
    result["clarification_required"] = plan.get("clarification_required")

    _show("plan status", result["plan_status"])
    _show("tasks", len(plan.get("tasks", [])))
    _show("required capabilities", result["capabilities"])
    _show("requires approval", result["requires_approval"])
    if result["missing_information"]:
        _show("missing information", result["missing_information"])
    if result["unsupported_operations"]:
        _show("unsupported operations", result["unsupported_operations"])
    if result["clarification_required"]:
        _show("clarification question", plan.get("clarification_question"))

    # --- execute ------------------------------------------------------
    execution = client.post(
        "/api/v1/execution/execute", json={"plan": plan}, timeout=120
    )
    if execution.status_code != 200:
        _show("execute HTTP", execution.status_code)
        result["execute_error"] = execution.text[:200]
        return result

    report = execution.json()["report"]
    result["execution_status"] = report.get("status")
    result["task_results"] = [
        {
            "capability": item.get("capability"),
            "status": item.get("status"),
            "error": item.get("error"),
        }
        for item in report.get("task_results", [])
    ]
    _show("execution status", result["execution_status"])
    for item in result["task_results"]:
        _show(
            f"  task {item['capability'] or '-'}",
            f"{item['status']}" + (f" — {item['error'][:60]}" if item.get("error") else ""),
        )

    return result


def main() -> int:
    """Run every scenario and print a summary."""
    print("NexusAI manual demonstration scenarios")
    print(f"Backend: {BASE}\n")

    # Prepare the corpus, as a reviewer would before the demonstration.
    with httpx.Client(base_url=BASE) as client:
        for path in (
            "data/sample/product_manual.md",
            "data/sample/meeting_notes.md",
        ):
            response = client.post(
                "/api/v1/documents/ingest", json={"path": path}, timeout=60
            )
            payload = response.json()["result"]
            print(f"ingest {path}: {payload['status']} ({payload.get('chunk_count')} chunks)")

        print()
        results = [run_scenario(client, scenario) for scenario in SCENARIOS]

    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for result in results:
        print(
            f"{result['id']}: intent={result.get('intent')} "
            f"plan={result.get('plan_status')} execution={result.get('execution_status')}"
        )

    output = Path(__file__).resolve().parents[1] / "results" / "manual_demo_scenarios.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nDetailed results written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
