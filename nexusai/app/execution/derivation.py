"""Derivation of tool inputs from a plan's own request.

A planner task names the capability it needs, but its template may not
carry every input that capability requires. The ``document.extract``
capability needs a query; the ``document.read`` capability needs a path.

Rather than inventing values, the executor derives them from the plan's
own ``original_request`` — the text the user actually wrote. The
derivations are explicit and narrow:

* a document reference in the request becomes the path for ``document.read``;
* the request itself becomes the query for ``document.extract`` and the
  question for ``llm.summarise``.

Anything a task already declares wins over a derived value. A derivation
that cannot be made leaves the input absent, so schema validation reports
it rather than the executor inventing one.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Matches a filename reference with a readable extension.
_DOCUMENT_REFERENCE_RE = re.compile(
    r"(?P<path>[\w./\\-]+\.(?:pdf|docx|txt|text|md|markdown))",
    re.IGNORECASE,
)


def find_document_reference(text: str) -> str | None:
    """Return the first document filename referenced in *text*.

    Args:
        text: The request text to search.

    Returns:
        The referenced path as written, or None when the request names no
        document.
    """
    match = _DOCUMENT_REFERENCE_RE.search(text)
    if not match:
        return None
    return match.group("path")


def derive_tool_inputs(
    capability: str,
    request: str,
    declared: dict[str, object],
) -> dict[str, object]:
    """Derive the inputs a capability needs from the request text.

    Args:
        capability: The capability about to be executed.
        request: The plan's original request.
        declared: The inputs the task already declares.

    Returns:
        The declared inputs, plus any derived value for an input the task
        did not supply.
    """
    resolved = dict(declared)

    if capability == "document.read" and not resolved.get("path"):
        reference = find_document_reference(request)
        if reference:
            resolved["path"] = reference

    if capability == "document.extract" and not resolved.get("query") and request.strip():
        resolved["query"] = request.strip()

    if capability == "llm.summarise" and not resolved.get("question") and request.strip():
        resolved["question"] = request.strip()

    return resolved


def derive_path(request: str) -> Path | None:
    """Return the document path referenced in *request*, if any."""
    reference = find_document_reference(request)
    return Path(reference) if reference else None
