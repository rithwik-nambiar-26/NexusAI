"""HTTP client for the Streamlit frontend.

The UI talks to the FastAPI backend over HTTP rather than importing the
services directly. That keeps one implementation of the business logic:
the backend is the single source of truth, and the UI is a client of it.

Every call goes through :func:`api_request`, which turns a transport or
HTTP error into a readable message the page can show. No response is
silently swallowed.
"""

from __future__ import annotations

from typing import Any

import httpx

from nexusai.app.ui.config import API_BASE_URL, REQUEST_TIMEOUT_SECONDS


class ApiError(Exception):
    """Raised when a backend call fails.

    The message is written for the person reading the screen, not for a
    log file.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


def _error_detail(response: httpx.Response) -> str:
    """Extract a readable message from an error response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        if code and message:
            return f"{message} ({code})"
        if message:
            return str(message)
    if isinstance(payload, dict) and payload.get("message"):
        return str(payload["message"])
    return f"HTTP {response.status_code}"


def api_request(
    method: str,
    path: str,
    *,
    base_url: str | None = None,
    json: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> Any:
    """Make a request to the NexusAI backend.

    Args:
        method: HTTP method.
        path: Path beginning with a slash, relative to the API root.
        base_url: Override for the backend base URL.
        json: JSON body.
        files: Multipart files.
        params: Query parameters.
        timeout: Request timeout in seconds.

    Returns:
        The decoded JSON response.

    Raises:
        ApiError: The backend was unreachable, or returned an error.
    """
    root = (base_url or API_BASE_URL).rstrip("/")
    url = f"{root}{path}"

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                url,
                json=json,
                files=files,
                params=params,
            )
    except httpx.ConnectError as exc:
        raise ApiError(
            f"Could not reach the NexusAI backend at {root}. "
            "Start it with: python -m nexusai serve"
        ) from exc
    except httpx.TimeoutException as exc:
        raise ApiError(f"The backend at {root} did not respond in time.") from exc
    except httpx.HTTPError as exc:
        raise ApiError(f"The request to {root} failed: {exc}") from exc

    if response.status_code >= 400:
        raise ApiError(_error_detail(response), status_code=response.status_code)

    try:
        return response.json()
    except ValueError as exc:
        raise ApiError("The backend returned a response that was not JSON.") from exc


def backend_is_reachable(base_url: str | None = None) -> tuple[bool, str]:
    """Report whether the backend is reachable.

    Returns:
        A tuple of (reachable, message).
    """
    root = (base_url or API_BASE_URL).rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"{root}/health")
    except httpx.HTTPError as exc:
        return False, f"Backend unreachable at {root}: {exc}"
    if response.status_code >= 400:
        return False, f"Backend at {root} returned HTTP {response.status_code}"
    return True, f"Backend reachable at {root}"


def classify_intent(text: str, base_url: str | None = None) -> dict[str, Any]:
    """Classify a request's intent."""
    return api_request(
        "POST", "/api/v1/intent/classify", json={"text": text}, base_url=base_url
    )


def create_plan(
    text: str,
    intent: str | None = None,
    intent_status: str | None = None,
    intent_confidence: float | None = None,
    source: str | None = None,
    source_documents: list[str] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Create a structured plan for a request.

    Args:
        text: The natural-language request.
        intent: The intent to plan for. When given, the planner uses it
            instead of resolving one itself.
        intent_status: The status of the classification the intent came
            from. A status of ``clarification_required`` makes the
            planner ask for clarification rather than plan.
        intent_confidence: The confidence of that classification.
        source: Where the intent came from — ``"classifier"`` when the
            classifier's own prediction is being planned, or
            ``"explicit"`` when the user chose it. Defaults to
            ``"explicit"`` when an intent is supplied, and to
            ``"classifier"`` otherwise.
        source_documents: The documents the request is about, when the
            user selected one or more. Every document capability in the
            plan is restricted to them. Several are given only when the
            request explicitly spans them.
        base_url: Override for the backend base URL.
    """
    payload: dict[str, Any] = {"text": text}
    if intent:
        payload["intent"] = intent
        payload["source"] = source or "explicit"
    elif source:
        payload["source"] = source
    if intent_status:
        payload["intent_status"] = intent_status
    if intent_confidence is not None:
        payload["intent_confidence"] = intent_confidence
    if source_documents:
        payload["source_documents"] = list(source_documents)
    return api_request(
        "POST", "/api/v1/planner/plan", json=payload, base_url=base_url
    )


def execute_plan(
    plan: dict[str, Any],
    approvals: list[dict[str, Any]] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Execute a plan and return the execution report.

    Args:
        plan: The plan to execute.
        approvals: Approval decisions to apply. An approval is bound to
            the task and to its validated inputs, so it is only honoured
            when it still matches.
        base_url: Override for the backend base URL.
    """
    payload: dict[str, Any] = {"plan": plan}
    if approvals:
        payload["approvals"] = approvals
    return api_request(
        "POST", "/api/v1/execution/execute", json=payload, base_url=base_url
    )


def approve_task(
    task_id: str,
    granted: bool = True,
    note: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Approve or deny a task that is awaiting approval.

    The backend holds the execution report in memory, so the decision is
    recorded against that report. The approved request is then re-sent
    with the next execution.
    """
    payload: dict[str, Any] = {"task_id": task_id, "granted": granted}
    if note:
        payload["note"] = note
    return api_request(
        "POST", "/api/v1/execution/approve", json=payload, base_url=base_url
    )


def list_documents(base_url: str | None = None) -> dict[str, Any]:
    """List the indexed documents."""
    return api_request("GET", "/api/v1/documents", base_url=base_url)


def ingest_document(
    path: str,
    name: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Ingest a document by path."""
    payload: dict[str, Any] = {"path": path}
    if name:
        payload["name"] = name
    return api_request(
        "POST", "/api/v1/documents/ingest", json=payload, base_url=base_url
    )


def ingest_upload(
    filename: str,
    content: bytes,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Ingest an uploaded file.

    The upload is sent to the backend's ingest-text endpoint after being
    written into the shared allowed-root area, so the same PathPolicy
    governs it as every other read.
    """
    payload = {"text": content.decode("utf-8", errors="replace"), "name": filename}
    return api_request(
        "POST", "/api/v1/documents/ingest-text", json=payload, base_url=base_url
    )


def retrieve_passages(
    query: str,
    top_k: int = 5,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Retrieve passages relevant to a query."""
    return api_request(
        "POST",
        "/api/v1/documents/retrieve",
        json={"query": query, "top_k": top_k},
        base_url=base_url,
    )


def answer_question(question: str, base_url: str | None = None) -> dict[str, Any]:
    """Answer a question from the indexed documents."""
    return api_request(
        "POST", "/api/v1/documents/answer", json={"question": question}, base_url=base_url
    )


def summarise_document(
    document_id: str | None = None,
    question: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Summarise a document, or the passages matching a question."""
    payload: dict[str, Any] = {}
    if document_id:
        payload["document_id"] = document_id
    if question:
        payload["question"] = question
    return api_request(
        "POST", "/api/v1/documents/summarise", json=payload, base_url=base_url
    )


def analyse_csv(
    path: str,
    group_by: str | None = None,
    measure: str | None = None,
    top_n: int = 10,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Analyse a CSV file through the registered data capability.

    This is an independent, explicitly triggered analysis. It needs no
    task plan, so it cannot be affected by a plan left over from another
    page.
    """
    payload: dict[str, Any] = {"path": path, "top_n": top_n}
    if group_by:
        payload["group_by"] = group_by
    if measure:
        payload["measure"] = measure
    return api_request(
        "POST", "/api/v1/documents/analyse-csv", json=payload, base_url=base_url
    )


def list_runs(
    limit: int = 50,
    base_url: str | None = None,
) -> dict[str, Any]:
    """List the persisted workflow runs."""
    return api_request(
        "GET", "/api/v1/workflows", params={"limit": limit}, base_url=base_url
    )


def create_reminder(
    message: str,
    due_at: str,
    timezone: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Store a reminder for a time the user names."""
    payload: dict[str, Any] = {"message": message, "due_at": due_at}
    if timezone:
        payload["timezone"] = timezone
    return api_request("POST", "/api/v1/reminders", json=payload, base_url=base_url)


def list_reminders(
    status: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """List the stored reminders."""
    params = {"status": status} if status else None
    return api_request("GET", "/api/v1/reminders", params=params, base_url=base_url)


def list_due_reminders(
    within_minutes: int = 0,
    base_url: str | None = None,
) -> dict[str, Any]:
    """List the reminders that are due."""
    return api_request(
        "GET",
        "/api/v1/reminders/due",
        params={"within_minutes": within_minutes},
        base_url=base_url,
    )


def cancel_reminder(reminder_id: int, base_url: str | None = None) -> dict[str, Any]:
    """Cancel a pending reminder."""
    return api_request(
        "DELETE", f"/api/v1/reminders/{reminder_id}", base_url=base_url
    )


def get_run(run_id: int, base_url: str | None = None) -> dict[str, Any]:
    """Fetch one workflow run with its steps."""
    return api_request("GET", f"/api/v1/workflows/{run_id}", base_url=base_url)


def list_execution_tools(base_url: str | None = None) -> dict[str, Any]:
    """List the registered execution capabilities."""
    return api_request("GET", "/api/v1/execution/tools", base_url=base_url)


def system_status(base_url: str | None = None) -> dict[str, Any]:
    """Fetch the system status."""
    return api_request("GET", "/api/v1/system/status", base_url=base_url)
