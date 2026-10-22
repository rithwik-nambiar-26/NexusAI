"""Planning service for structured task decomposition and plan validation.

The planner is deterministic: given an intent it produces a typed plan with
an explicit dependency graph. It never executes anything. Controlled
execution belongs to Day 5.

An optional local LLM planner could be added behind :class:`PlanningStrategy`
without changing callers, but no LLM is required to run NexusAI or its tests.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from nexusai.app.core.logging import get_logger
from nexusai.ml.planner.schemas import (
    APPROVAL_REQUIRED_TASK_TYPES,
    Plan,
    PlanStatus,
    Task,
    TaskParameter,
    TaskType,
)
from nexusai.ml.schemas import ClassificationStatus, IntentCategory

logger = get_logger("ml.planner")

#: Wording that means the user wants a reminder cancelled.
_REMINDER_CANCEL_WORDS = ("cancel", "remove", "delete", "drop", "stop")

#: Wording that means the user wants the reminders listed.
_REMINDER_LIST_WORDS = (
    "list",
    "show",
    "what reminders",
    "which reminders",
    "my reminders",
    "do i have",
    "upcoming",
)


def _strip_file_references(text: str) -> str:
    """Remove file and path references from *text*.

    Used when looking for topical markers in the prose of a request, so that
    a filename such as ``sales_2026.csv`` is not read as the user asking for
    a sales measure.
    """
    without_paths = re.sub(r"[\w./-]+\.(?:md|pdf|txt|docx|csv|json|tsv|xlsx|parquet)", " ", text)
    return re.sub(r"\s+", " ", without_paths).strip()


class PlanValidationError(Exception):
    """Raised when a plan cannot be produced or fails structural validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class PlanningStrategy(Protocol):
    """Interface for a planning backend.

    The default implementation is :class:`PlannerService`. A local LLM
    adapter may implement this protocol later; the interface keeps the
    planner replaceable without a paid or mandatory external dependency.
    """

    def plan(
        self,
        request: str,
        intent: str | None,
        entities: dict[str, Any] | None,
    ) -> Plan: ...


class PlannerService:
    """Deterministic structured planner.

    Decomposes a request into typed tasks according to the intent taxonomy,
    wires explicit dependencies between them, and validates the resulting
    plan.
    """

    def __init__(self) -> None:
        """Initialise the planner with task templates for each intent."""
        self._task_templates = self._build_task_templates()

    def _build_task_templates(self) -> dict[str, list[dict[str, Any]]]:
        """Build task templates for each supported intent category.

        Templates define the canonical task structure per intent. They are
        workflow patterns, not responses to particular requests: the same
        pattern is reused across many phrasings, and request-specific detail
        is carried in task parameters rather than in new task shapes.
        """
        templates = {
            IntentCategory.DOCUMENT_QUESTION_ANSWERING.value: [
                {
                    "task_type": TaskType.DOCUMENT_READ,
                    "task_name": "Locate and read the source document",
                    "description": "Resolve the referenced document and load its content.",
                    "required_capabilities": ["document.read"],
                    "expected_output": "Document content available for extraction.",
                    "verification_criteria": "The referenced document was located and read.",
                },
                {
                    "task_type": TaskType.DOCUMENT_EXTRACT,
                    "task_name": "Extract passages relevant to the question",
                    "description": "Extract the passages that address the specific question asked.",
                    "required_capabilities": ["document.extract"],
                    "expected_output": "Candidate passages with source spans.",
                    "verification_criteria": "Extracted passages are present and non-empty.",
                },
                {
                    "task_type": TaskType.VERIFY_CONTENT,
                    "task_name": "Verify the answer against the extracted passages",
                    "description": "Check that every claim in the answer is supported by an extracted passage.",
                    "required_capabilities": ["verify.content"],
                    "expected_output": "Per-claim verification result with supporting spans.",
                    "verification_criteria": "No claim is unsupported by the extracted evidence.",
                },
            ],
            IntentCategory.DOCUMENT_SUMMARISATION.value: [
                {
                    "task_type": TaskType.DOCUMENT_READ,
                    "task_name": "Locate and read the source document",
                    "description": "Resolve the referenced document and load its content.",
                    "required_capabilities": ["document.read"],
                    "expected_output": "Document content available for extraction.",
                    "verification_criteria": "The referenced document was located and read.",
                },
                {
                    "task_type": TaskType.DOCUMENT_EXTRACT,
                    "task_name": "Extract the key points",
                    "description": "Extract the main ideas and supporting points from the document.",
                    "required_capabilities": ["document.extract"],
                    "expected_output": "Ordered list of key points with source spans.",
                    "verification_criteria": "Extracted points are present and non-empty.",
                },
                {
                    "task_type": TaskType.DOCUMENT_SUMMARISE,
                    "task_name": "Produce the summary",
                    "description": "Write the summary from the extracted key points only.",
                    "required_capabilities": ["llm.summarise"],
                    "expected_output": "Summary text satisfying the requested format.",
                    "verification_criteria": "The summary contains only claims present in the extracted points.",
                },
                {
                    "task_type": TaskType.VERIFY_CONTENT,
                    "task_name": "Verify the summary against the source",
                    "description": "Check that the summary is supported by the extracted content.",
                    "required_capabilities": ["verify.content"],
                    "expected_output": "Verification result with any unsupported claims listed.",
                    "verification_criteria": "Every summary claim is supported by extracted evidence.",
                },
            ],
            IntentCategory.DOCUMENT_EXTRACTION.value: [
                {
                    "task_type": TaskType.DOCUMENT_READ,
                    "task_name": "Locate and read the source document",
                    "description": "Resolve the referenced document and load its content.",
                    "required_capabilities": ["document.read"],
                    "expected_output": "Document content available for extraction.",
                    "verification_criteria": "The referenced document was located and read.",
                },
                {
                    "task_type": TaskType.DOCUMENT_EXTRACT,
                    "task_name": "Extract the requested information",
                    "description": "Extract the specific information requested (headings, dates, tables, entities).",
                    "required_capabilities": ["document.extract"],
                    "expected_output": "Extracted items with source spans.",
                    "verification_criteria": "Extracted items match the requested information type.",
                },
                {
                    "task_type": TaskType.VERIFY_CONTENT,
                    "task_name": "Verify the extraction against the source",
                    "description": "Check that every extracted item appears in the source document.",
                    "required_capabilities": ["verify.content"],
                    "expected_output": "Verification result listing any unsupported extractions.",
                    "verification_criteria": "No extracted item is absent from the source.",
                },
            ],
            IntentCategory.DOCUMENT_TRANSFORMATION.value: [
                {
                    "task_type": TaskType.DOCUMENT_READ,
                    "task_name": "Locate and read the source document",
                    "description": "Resolve the referenced document and load its content.",
                    "required_capabilities": ["document.read"],
                    "expected_output": "Source document content available for transformation.",
                    "verification_criteria": "The source document was located and read.",
                },
                {
                    "task_type": TaskType.DOCUMENT_TRANSFORM,
                    "task_name": "Transform the document into the target format",
                    "description": "Convert the document into the requested output format.",
                    "required_capabilities": ["document.transform"],
                    "expected_output": "Transformed document in the target format.",
                    "verification_criteria": "The output is in the requested format.",
                },
                {
                    "task_type": TaskType.DOCUMENT_WRITE,
                    "task_name": "Write the transformed document to the target path",
                    "description": "Persist the transformed document at the requested location.",
                    "required_capabilities": ["filesystem.write"],
                    "expected_output": "File written at the target path.",
                    "verification_criteria": "The target file exists and matches the transformed content.",
                },
                {
                    "task_type": TaskType.VERIFY_CONTENT,
                    "task_name": "Verify the transformation preserved content",
                    "description": "Check that the transformed document preserves the source content.",
                    "required_capabilities": ["verify.content"],
                    "expected_output": "Verification result for content preservation.",
                    "verification_criteria": "No source content was lost in the transformation.",
                },
            ],
            IntentCategory.DATA_ANALYSIS.value: [
                {
                    "task_type": TaskType.DATA_LOAD,
                    "task_name": "Load the data file",
                    "description": "Load the referenced CSV or tabular data file and confirm it parses.",
                    "required_capabilities": ["data.load"],
                    "expected_output": "Loaded table with the source columns available.",
                    "verification_criteria": "The data file loaded and parsed without error.",
                },
                {
                    "task_type": TaskType.DATA_ANALYSE,
                    "task_name": "Profile the relevant columns",
                    "description": "Inspect the columns needed for the requested analysis.",
                    "required_capabilities": ["data.analyse"],
                    "expected_output": "Column profile with types and usable values.",
                    "verification_criteria": "The columns required by the analysis are present and populated.",
                },
                {
                    "task_type": TaskType.DATA_AGGREGATE,
                    "task_name": "Compute the requested aggregation",
                    "description": "Apply the aggregation the request asks for (sum, mean, top-N, growth).",
                    "required_capabilities": ["data.aggregate"],
                    "expected_output": "Aggregated values with the grouping keys retained.",
                    "verification_criteria": "The aggregation matches the requested measure and grouping.",
                },
                {
                    "task_type": TaskType.VERIFY_CALCULATION,
                    "task_name": "Verify the calculation",
                    "description": "Independently recompute the aggregation to confirm the result.",
                    "required_capabilities": ["verify.calculation"],
                    "expected_output": "Verification result for the computed values.",
                    "verification_criteria": "The independently recomputed values match the reported values.",
                },
                {
                    "task_type": TaskType.DATA_EXPORT,
                    "task_name": "Report the analysis result",
                    "description": "Present the verified result in the requested form.",
                    "required_capabilities": ["data.export"],
                    "expected_output": "Analysis result in the requested output format.",
                    "verification_criteria": "The reported result contains the verified values.",
                },
            ],
            IntentCategory.RESEARCH.value: [
                {
                    "task_type": TaskType.RESEARCH_QUERY,
                    "task_name": "Identify the research question",
                    "description": "Restate the request as specific research questions.",
                    "required_capabilities": ["research.query"],
                    "expected_output": "Explicit research questions and inclusion criteria.",
                    "verification_criteria": "The research questions are specific and answerable.",
                },
                {
                    "task_type": TaskType.RESEARCH_FETCH,
                    "task_name": "Retrieve source material",
                    "description": "Retrieve candidate sources for the research questions.",
                    "required_capabilities": ["web.search", "web.fetch"],
                    "expected_output": "Candidate sources with retrieval provenance.",
                    "verification_criteria": "At least one retrievable source per research question.",
                },
                {
                    "task_type": TaskType.RESEARCH_EXTRACT,
                    "task_name": "Extract evidence and citations",
                    "description": "Extract the passages that support or contradict each research question.",
                    "required_capabilities": ["llm.extract"],
                    "expected_output": "Evidence passages with citations per research question.",
                    "verification_criteria": "Each research question has at least one cited passage.",
                },
                {
                    "task_type": TaskType.RESEARCH_SYNTHESISE,
                    "task_name": "Synthesise the findings",
                    "description": "Combine the extracted evidence into findings that answer the questions.",
                    "required_capabilities": ["llm.summarise"],
                    "expected_output": "Findings with citations to the supporting passages.",
                    "verification_criteria": "Every claim in the findings carries a citation.",
                },
                {
                    "task_type": TaskType.VERIFY_CONTENT,
                    "task_name": "Verify the conclusions are supported",
                    "description": "Check that each conclusion follows from the cited evidence.",
                    "required_capabilities": ["verify.content"],
                    "expected_output": "Verification result listing unsupported conclusions.",
                    "verification_criteria": "No conclusion is unsupported by the cited evidence.",
                },
            ],
            IntentCategory.COMMUNICATION.value: [
                {
                    "task_type": TaskType.COMMUNICATION_DRAFT,
                    "task_name": "Draft the message",
                    "description": "Compose the message content for the requested recipient.",
                    "required_capabilities": ["communication.draft"],
                    "expected_output": "Draft message text ready to send.",
                    "verification_criteria": "The draft contains the content the request specified.",
                },
                {
                    "task_type": TaskType.COMMUNICATION_SEND,
                    "task_name": "Send the message",
                    "description": "Send the drafted message through the requested channel.",
                    "required_capabilities": ["communication.send"],
                    "expected_output": "Send confirmation with the resolved recipient.",
                    "verification_criteria": "The message was accepted by the channel for the intended recipient.",
                },
            ],
        }

        # The reminder workflows have more than one shape, because "set a
        # reminder", "list my reminders" and "cancel a reminder" are three
        # different actions. The shape is chosen from the request's own
        # wording, and each shape is a single registered capability.
        templates[IntentCategory.REMINDER.value] = [
            {
                "task_type": TaskType.REMINDER_CREATE,
                "task_name": "Store the reminder",
                "description": (
                    "Store the reminder with the due time the request names, "
                    "and schedule it for that time."
                ),
                "required_capabilities": ["reminder.create"],
                "expected_output": "The stored reminder with its due time.",
                "verification_criteria": (
                    "The reminder was stored with a due time in the future."
                ),
            },
            {
                "task_type": TaskType.REMINDER_LIST,
                "task_name": "List the reminders",
                "description": "Report the reminders that are currently stored.",
                "required_capabilities": ["reminder.list"],
                "expected_output": "The stored reminders with their due times and statuses.",
                "verification_criteria": "The stored reminders are reported.",
            },
            {
                "task_type": TaskType.REMINDER_CANCEL,
                "task_name": "Cancel the reminder",
                "description": "Cancel the pending reminder the request names.",
                "required_capabilities": ["reminder.cancel"],
                "expected_output": "The cancelled reminder.",
                "verification_criteria": "The named reminder is no longer pending.",
            },
        ]

        return templates

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def plan(
        self,
        request: str,
        intent: str | None = None,
        entities: dict[str, Any] | None = None,
    ) -> Plan:
        """Create a structured plan for *request*.

        Args:
            request: The natural-language user request.
            intent: The intent to plan for. When omitted the caller is
                expected to have resolved the intent already.
            entities: Entities extracted from the request.

        Returns:
            A validated :class:`Plan`.
        """
        plan, _ = self.create_plan(
            request=request,
            intent=intent,
            entities=entities,
            source="explicit",
        )
        return plan

    def create_plan(
        self,
        request: str,
        intent: str | None = None,
        intent_confidence: float = 0.0,
        intent_status: str = ClassificationStatus.CONFIDENT.value,
        entities: dict[str, Any] | None = None,
        source: str = "classifier",
        classifier_intent: str | None = None,
        classifier_status: str | None = None,
    ) -> tuple[Plan, list[str]]:
        """Create a structured plan and report any warnings.

        Args:
            request: The natural-language user request.
            intent: Intent to plan for, if already resolved.
            intent_confidence: Confidence reported by the intent classifier.
            intent_status: Status reported by the intent classifier.
            entities: Entities extracted from the request.
            source: ``"classifier"`` or ``"explicit"``; recorded on the plan
                so downstream consumers can tell how the intent was obtained.
            classifier_intent: The classifier's own top-ranked prediction for
                the request, when it differs from the intent being planned.
            classifier_status: The status of that prediction. It is recorded
                separately from ``intent_status`` because an explicitly
                chosen intent is always treated as confident, while the
                classifier's original verdict is not.

        Returns:
            A tuple of the plan and a list of warnings.
        """
        warnings: list[str] = []

        if intent is None:
            plan = self._create_error_plan(
                request,
                "No intent available: the classifier did not return a usable intent.",
            )
            return plan, ["No intent available to plan against"]

        try:
            intent_enum = IntentCategory(intent)
        except ValueError:
            plan = self._create_error_plan(request, f"Unknown intent: {intent}")
            return plan, [f"Unknown intent: {intent}"]

        # A confident destructive classification may not be redirected to
        # another intent. See _destructive_redirect_guard.
        redirect_warning = self._destructive_redirect_guard(
            intent_enum, classifier_intent, classifier_status
        )
        if redirect_warning is not None:
            plan = self._create_destructive_redirect_plan(
                request, intent, source, classifier_intent
            )
            return plan, [redirect_warning]

        # A weaker destructive signal is not strong enough to refuse the
        # request, but it is recorded on the plan so the destructive part of
        # the request is never silently dropped.
        destructive_note = self._destructive_signal_note(
            intent_enum, classifier_intent
        )

        # A low-confidence classification is not treated as ground truth.
        if intent_status == ClassificationStatus.CLARIFICATION_REQUIRED.value:
            plan = self._create_clarification_plan(request, intent, intent_confidence)
            return plan, ["Intent classification requires clarification"]

        if intent_status in (
            ClassificationStatus.ABSTAINED.value,
            ClassificationStatus.ERROR.value,
        ):
            plan = self._create_error_plan(request, f"Intent classification status: {intent_status}")
            return plan, [f"Intent classification did not succeed: {intent_status}"]

        if intent_enum in IntentCategory.special():
            plan = self._create_special_plan(request, intent_enum)
            return plan, [f"Intent '{intent}' requires special handling"]

        plan = self._create_plan_from_template(
            request=request,
            intent=intent_enum,
            entities=entities or {},
            source=source,
        )

        if destructive_note:
            plan.unsupported_operations.append(destructive_note)
            plan.requires_approval = True
            plan.approval_reasons.append(
                "The classifier identified a destructive pattern in the request, "
                "so the plan is marked for approval before it is executed."
            )

        errors = plan.validate()
        if errors:
            plan.plan_status = PlanStatus.INVALID
            plan.validation_errors = errors
            warnings.extend(errors)
        else:
            plan.plan_status = PlanStatus.READY

        logger.info(
            "Plan created",
            extra={
                "plan_id": plan.plan_id,
                "intent": plan.intent,
                "n_tasks": len(plan.tasks),
                "plan_status": plan.plan_status.value,
            },
        )

        return plan, warnings

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _destructive_top1(
        intent_enum: IntentCategory,
        classifier_intent: str | None,
    ) -> bool:
        """Return True when the classifier's top intent was destructive.

        "Top intent" means the classifier's own highest-scoring prediction,
        which is not necessarily the intent being planned.
        """
        if classifier_intent is None:
            return False
        if classifier_intent != IntentCategory.DESTRUCTIVE_OPERATION.value:
            return False
        return intent_enum != IntentCategory.DESTRUCTIVE_OPERATION

    @classmethod
    def _destructive_redirect_guard(
        cls,
        intent_enum: IntentCategory,
        classifier_intent: str | None,
        classifier_status: str | None,
    ) -> str | None:
        """Refuse to redirect a confident destructive classification.

        A caller may assert an intent explicitly — the confirmation flow in
        the UI does exactly that. That assertion must not be able to erase
        the classifier's own verdict that the request is destructive, so a
        confident destructive prediction blocks a redirect to any other
        intent.

        The guard is deliberately narrow, because the classifier is weak on
        this class: its per-class F1 for ``destructive_operation`` is 0.00
        on the held-out set, and it scores benign phrasings such as "how do
        I delete my old backups safely" within the same range as genuine
        destructive commands. A *confident* destructive prediction is a
        usable signal; a low-confidence one is not, so it is recorded on the
        plan instead of refusing it.

        The guard does not fire when the caller selected the destructive
        intent itself — that path is already refused by the special-intent
        handling.

        Returns:
            A warning message when the redirect must be refused, otherwise
            ``None``.
        """
        if not cls._destructive_top1(intent_enum, classifier_intent):
            return None
        if classifier_status != ClassificationStatus.CONFIDENT.value:
            return None
        return (
            "The classifier identified this request as a destructive operation "
            "with confidence, so it cannot be planned as a different intent."
        )

    @classmethod
    def _destructive_signal_note(
        cls,
        intent_enum: IntentCategory,
        classifier_intent: str | None,
    ) -> str | None:
        """Return the note recording a weaker destructive signal.

        When the classifier's top intent was destructive but not
        confidently so, the request is planned for the chosen intent and the
        destructive signal is recorded. The note appears in the plan's
        unsupported operations, so the destructive part of the request is
        reported rather than silently dropped.
        """
        if not cls._destructive_top1(intent_enum, classifier_intent):
            return None
        return (
            "The classifier identified a destructive pattern in this request. "
            "No destructive action will be taken, and no destructive "
            "capability is registered."
        )

    def _create_destructive_redirect_plan(
        self,
        request: str,
        intent: str | None,
        source: str,
        classifier_intent: str | None,
    ) -> Plan:
        """Create the plan returned when a destructive redirect is refused.

        The plan has no tasks. It exists to say clearly that the request was
        recognised as destructive and that choosing a different intent does
        not remove that recognition.
        """
        plan = Plan(
            original_request=request,
            intent=intent,
            plan_status=PlanStatus.INVALID,
            clarification_required=True,
            clarification_question=(
                "This request looks like a destructive operation, so NexusAI "
                "will not plan it as a different kind of task. Rephrase it to "
                "say what you want done with the files, and it will be "
                "classified again."
            ),
            source=source,
        )
        plan.requires_approval = True
        plan.approval_reasons.append(
            "The classifier detected a destructive operation; planning it as "
            "another intent requires a rephrased request."
        )
        plan.validation_errors = [
            f"Intent '{classifier_intent}' was classified with confidence and "
            "cannot be redirected to a different intent."
        ]
        return plan

    def _create_clarification_plan(
        self, request: str, intent: str | None, confidence: float
    ) -> Plan:
        """Create a plan that asks the user for clarification."""
        plan = Plan(
            original_request=request,
            intent=intent,
            plan_status=PlanStatus.INVALID,
            clarification_required=True,
            clarification_question=(
                "I'm not confident about what you're asking for. "
                "Could you say which of these you want: reading and answering "
                "questions about a document, summarising a document, analysing "
                "a data file, researching a topic, or sending a message?"
            ),
            source="classifier",
        )
        plan.validation_errors = [
            f"Intent classification confidence {confidence:.2f} is below the "
            "planner's planning threshold; clarification required."
        ]
        return plan

    def _create_error_plan(self, request: str, reason: str) -> Plan:
        """Create a plan for a request that cannot be planned at all."""
        return Plan(
            original_request=request,
            plan_status=PlanStatus.INVALID,
            validation_errors=[reason],
            source="classifier",
        )

    def _create_special_plan(self, request: str, intent: IntentCategory) -> Plan:
        """Create a plan for intents that must not become executable plans."""
        plan = Plan(
            original_request=request,
            intent=intent.value,
            plan_status=PlanStatus.INVALID,
            clarification_required=True,
            source="classifier",
        )

        if intent == IntentCategory.DESTRUCTIVE_OPERATION:
            plan.clarification_question = (
                "This request would delete or overwrite data. "
                "Confirm explicitly if you want to proceed."
            )
            plan.requires_approval = True
            plan.approval_reasons.append(
                "Destructive operation requires explicit user approval before execution."
            )
        elif intent == IntentCategory.INFEASIBLE:
            plan.clarification_question = (
                "This goal cannot be completed with the available capabilities. "
                "Could you restate it in terms of what the tools can do?"
            )
        elif intent == IntentCategory.OUT_OF_SCOPE:
            plan.clarification_question = (
                "This request is outside the supported scope. "
                "Could you ask about a task NexusAI can help with?"
            )
        elif intent == IntentCategory.CHANNEL_UNAVAILABLE:
            plan.clarification_question = (
                "The requested messaging channel is not available. "
                "Could you use an available channel instead?"
            )
        elif intent == IntentCategory.INVALID:
            plan.clarification_question = (
                "I could not understand that request. Could you rephrase it?"
            )

        plan.validation_errors = [f"Intent '{intent.value}' cannot be planned automatically."]
        return plan

    def _create_plan_from_template(
        self,
        request: str,
        intent: IntentCategory,
        entities: dict[str, Any],
        source: str,
    ) -> Plan:
        """Build a plan from the template registered for *intent*."""
        template = self._task_templates.get(intent.value, [])

        if intent == IntentCategory.REMINDER:
            template = self._reminder_template(request)

        plan = Plan(
            original_request=request,
            intent=intent.value,
            plan_status=PlanStatus.DRAFT,
            source=source,
        )

        for entry in template:
            task = Task(
                task_name=entry["task_name"],
                description=entry["description"],
                task_type=entry["task_type"],
                expected_output=entry["expected_output"],
                required_capabilities=list(entry.get("required_capabilities", [])),
                verification_criteria=entry.get("verification_criteria"),
            )
            plan.add_task(task)

        # Chain the tasks: each depends on its predecessor. The dependency
        # pairs are recorded on the plan and mirrored onto each task so both
        # representations stay consistent.
        for index, task in enumerate(plan.tasks):
            if index == 0:
                continue
            previous = plan.tasks[index - 1]
            task.dependencies = [previous.task_id]
            plan.dependencies.append((previous.task_id, task.task_id))

        if entities:
            plan.tasks[0].input_parameters.append(
                TaskParameter(
                    name="entities",
                    value=entities,
                    description="Entities extracted from the user request",
                    required=False,
                )
            )

        self._apply_safety_rules(plan)
        self._detect_missing_information(plan, request, intent)
        self._detect_unsupported_operations(plan, request)

        return plan

    def _reminder_template(self, request: str) -> list[dict[str, Any]]:
        """Return the reminder task shape that matches the request.

        "Set a reminder for 7 AM", "list my reminders" and "cancel my
        reminder" all belong to the same intent but call for different
        capabilities. The wording decides which one, and the wording is
        the user's own.

        The order matters: a request that both mentions cancelling and
        mentions a time is treated as a cancellation, because cancelling
        is the action the verb names.
        """
        lowered = request.lower()
        templates = self._task_templates.get(IntentCategory.REMINDER.value, [])
        by_type = {
            entry["task_type"]: entry for entry in templates
        }

        if any(word in lowered for word in _REMINDER_CANCEL_WORDS):
            return [by_type[TaskType.REMINDER_CANCEL]]
        if any(word in lowered for word in _REMINDER_LIST_WORDS):
            return [by_type[TaskType.REMINDER_LIST]]
        return [by_type[TaskType.REMINDER_CREATE]]

    def _apply_safety_rules(self, plan: Plan) -> None:
        """Flag tasks that require approval before they may be executed."""
        for task in plan.tasks:
            if task.task_type in APPROVAL_REQUIRED_TASK_TYPES:
                plan.requires_approval = True
                reason = (
                    f"Task '{task.task_name}' performs a state-changing operation "
                    f"({task.task_type.value}) and requires explicit approval."
                )
                if reason not in plan.approval_reasons:
                    plan.approval_reasons.append(reason)

    def _detect_missing_information(
        self, plan: Plan, request: str, intent: IntentCategory
    ) -> None:
        """Record information the plan needs that the request did not supply."""
        lowered = request.lower()
        # Measure and topic markers are looked for in the prose only: a
        # filename such as ``sales_2026.csv`` must not be mistaken for the
        # user asking for a sales measure.
        prose = _strip_file_references(lowered)

        document_intents = (
            IntentCategory.DOCUMENT_QUESTION_ANSWERING,
            IntentCategory.DOCUMENT_SUMMARISATION,
            IntentCategory.DOCUMENT_EXTRACTION,
            IntentCategory.DOCUMENT_TRANSFORMATION,
        )
        document_markers = (".md", ".pdf", ".txt", ".docx", "document", "file")
        data_markers = (".csv", ".json", ".tsv", "sales_2026", "data")
        measure_markers = (
            "revenue", "sales", "total", "average", "top", "growth", "profit", "count",
        )
        topic_markers = ("research", "compare", "find", "look up", "best", " vs ")
        recipient_markers = ("@", "email", "phone", "recipient", "team", "client")

        if intent in document_intents and not any(
            marker in lowered for marker in document_markers
        ):
            plan.missing_information.append(
                "No source document was referenced; the plan needs a document path."
            )

        if intent == IntentCategory.DATA_ANALYSIS:
            if not any(marker in lowered for marker in data_markers):
                plan.missing_information.append(
                    "No data file was referenced; the plan needs a dataset path."
                )
            if not any(marker in prose for marker in measure_markers):
                plan.missing_information.append(
                    "The measure to compute was not specified (e.g. revenue, average, top-N)."
                )

        if intent == IntentCategory.RESEARCH and not any(
            marker in prose for marker in topic_markers
        ):
            plan.missing_information.append(
                "The research topic was not stated in the request."
            )

        if intent == IntentCategory.COMMUNICATION and not any(
            marker in lowered for marker in recipient_markers
        ):
            plan.missing_information.append(
                "The recipient of the message was not identified in the request."
            )

        if intent == IntentCategory.REMINDER:
            self._detect_missing_reminder_information(plan, request)

        if not plan.tasks:
            plan.missing_information.append("No tasks could be derived for this intent.")

    def _detect_missing_reminder_information(self, plan: Plan, request: str) -> None:
        """Record what a reminder request did not supply.

        A reminder without a time cannot be scheduled, and one without
        anything to be reminded about is not a reminder. Both are reported
        rather than filled in with a value NexusAI invented.
        """
        from nexusai.app.services.reminder_time import ReminderTimeError, parse_due_at

        lowered = request.lower()
        is_create = any(
            task.task_type == TaskType.REMINDER_CREATE for task in plan.tasks
        )
        if not is_create:
            return

        try:
            parse_due_at(request)
        except ReminderTimeError as exc:
            if exc.code == "ambiguous_time":
                plan.missing_information.append(
                    f"The time in the request is ambiguous ({exc}). "
                    "Say whether it is in the morning or the evening."
                )
            else:
                plan.missing_information.append(
                    f"The request does not say when the reminder is due ({exc})."
                )

        if "remind" not in lowered and "alarm" not in lowered:
            plan.missing_information.append(
                "The request does not say what the reminder is about."
            )

    def _detect_unsupported_operations(self, plan: Plan, request: str) -> None:
        """Record operations the request asks for that the planner cannot do."""
        lowered = request.lower()

        unsupported_markers = {
            "execute code": "Code execution is not supported by the planner.",
            "run script": "Script execution is not supported by the planner.",
            "install package": "Package installation is not supported by the planner.",
            "deploy": "Deployment is not supported by the planner.",
            "schedule recurring": "Recurring scheduling is not supported by the planner.",
            "send to everyone": "Broadcasting is not supported by the planner.",
        }

        for marker, message in unsupported_markers.items():
            if marker in lowered and message not in plan.unsupported_operations:
                plan.unsupported_operations.append(message)


# ----------------------------------------------------------------------
# Module-level convenience
# ----------------------------------------------------------------------
_service: PlannerService | None = None


def get_planner_service() -> PlannerService:
    """Return the shared planner service instance."""
    global _service
    if _service is None:
        _service = PlannerService()
    return _service


def reset_planner_service() -> None:
    """Reset the shared planner service (used by tests)."""
    global _service
    _service = None


def create_plan(
    request: str,
    intent: str | None = None,
    intent_confidence: float = 0.0,
    intent_status: str = ClassificationStatus.CONFIDENT.value,
    entities: dict[str, Any] | None = None,
    source: str = "classifier",
    classifier_intent: str | None = None,
    classifier_status: str | None = None,
) -> tuple[Plan, list[str]]:
    """Create a plan using the shared planner service.

    Thin wrapper kept for convenience and for backwards compatibility with
    the Day 3 API surface.
    """
    return get_planner_service().create_plan(
        request=request,
        intent=intent,
        intent_confidence=intent_confidence,
        intent_status=intent_status,
        entities=entities,
        source=source,
        classifier_intent=classifier_intent,
        classifier_status=classifier_status,
    )
