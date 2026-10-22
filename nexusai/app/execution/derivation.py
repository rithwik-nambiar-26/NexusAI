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
    r"(?P<path>[\w./\\-]+\.(?:pdf|docx|txt|text|md|markdown|csv|tsv))",
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
    indexed_documents: list[str] | None = None,
) -> dict[str, object]:
    """Derive the inputs a capability needs from the request text.

    Args:
        capability: The capability about to be executed.
        request: The plan's original request.
        declared: The inputs the task already declares.
        indexed_documents: The document ids currently indexed. Used only
            to resolve a request that refers to a document without naming
            a file.

    Returns:
        The declared inputs, plus any derived value for an input the task
        did not supply.
    """
    resolved = dict(declared)

    if capability == "document.read" and not resolved.get("path") and not resolved.get(
        "document_id"
    ):
        # A document the user selected is used as it is: the request text
        # is not consulted for a filename, because the selection is the
        # more specific instruction and must not be overridden by a
        # guess.
        reference = find_document_reference(request)
        if reference:
            resolved["path"] = reference
        else:
            # The request refers to a document without naming a file, for
            # example "the uploaded product manual". When exactly one
            # document is indexed there is no ambiguity, so it is used.
            # With several, nothing is derived and the input stays absent,
            # so the plan asks rather than guessing.
            fallback = _single_indexed_document(request, indexed_documents)
            if fallback:
                resolved["document_id"] = fallback

    if capability in _DATA_CAPABILITIES and not resolved.get("path"):
        # A data-analysis request names its file, for example
        # "Analyse sales_2026.csv". The file is resolved under the allowed
        # roots by the path policy, so the bare name is enough here.
        reference = find_document_reference(request)
        if reference:
            resolved["path"] = reference

    if capability in _DATA_CAPABILITIES:
        # The request may name the column to group by and the measure to
        # aggregate, for example "the region with the highest revenue".
        if not resolved.get("group_by"):
            group = _find_group_column(request)
            if group:
                resolved["group_by"] = group
        if not resolved.get("measure"):
            measure = _find_measure_column(request)
            if measure:
                resolved["measure"] = measure

    if capability == "document.extract" and not resolved.get("query") and request.strip():
        resolved["query"] = request.strip()

    if capability == "llm.summarise" and not resolved.get("question") and request.strip():
        resolved["question"] = request.strip()

    if capability == "reminder.create" and request.strip():
        # The request carries both what the reminder is about and when it
        # is due. The time is parsed by the capability, so the whole
        # request is offered and the capability reads the time out of it.
        if not resolved.get("message"):
            resolved["message"] = request.strip()
        if not resolved.get("due_at"):
            resolved["due_at"] = request.strip()

    return resolved


#: The capabilities that read a data file and so need a path.
_DATA_CAPABILITIES = ("data.load", "data.analyse")


#: Wording that signals the user means a document without naming one.
_DOCUMENT_REFERENCE_WORDS = (
    "the document",
    "the uploaded",
    "the manual",
    "the notes",
    "the file",
    "uploaded document",
    "uploaded file",
    "uploaded manual",
)


#: Column names that a request is likely to name as a grouping column.
_GROUP_HINTS = (
    "region",
    "product",
    "category",
    "country",
    "city",
    "segment",
    "channel",
    "date",
    "month",
    "quarter",
)

#: Column names that a request is likely to name as a measure.
_MEASURE_HINTS = (
    "revenue",
    "units",
    "sales",
    "price",
    "profit",
    "cost",
    "total",
    "amount",
    "quantity",
)


def _find_group_column(request: str) -> str | None:
    """Return a grouping column named in the request, if any."""
    lowered = request.lower()
    for hint in _GROUP_HINTS:
        if hint in lowered:
            return hint
    return None


def _find_measure_column(request: str) -> str | None:
    """Return a measure column named in the request, if any."""
    lowered = request.lower()
    for hint in _MEASURE_HINTS:
        if hint in lowered:
            return hint
    return None


def _single_indexed_document(
    request: str,
    indexed_documents: list[str] | None,
) -> str | None:
    """Return the only indexed document when the request clearly means one.

    Returns None when the request names no document, or when several are
    indexed and the choice would be a guess.
    """
    if not indexed_documents or len(indexed_documents) != 1:
        return None

    lowered = request.lower()
    if not any(word in lowered for word in _DOCUMENT_REFERENCE_WORDS):
        return None

    return indexed_documents[0]


def derive_path(request: str) -> Path | None:
    """Return the document path referenced in *request*, if any."""
    reference = find_document_reference(request)
    return Path(reference) if reference else None
