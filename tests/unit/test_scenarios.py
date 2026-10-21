"""Validation tests for the experimental scenario suite.

These tests enforce the scenario file format documented in
``experiments/scenarios/README.md`` so that the suite is machine-checked
rather than relying on manual inspection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "experiments" / "scenarios"
SCENARIO_FILES = sorted(SCENARIO_DIR.glob("SC-*.json"))

VALID_CATEGORIES = {
    "simple_task",
    "multi_step",
    "dependency_ordering",
    "document_grounded",
    "insufficient_evidence",
    "data_analysis",
    "invalid_input",
    "unknown_tool",
    "tool_execution_failure",
    "transient_failure",
    "permanent_failure",
    "verification_failure",
    "recovery_and_replanning",
    "ambiguous_goal",
    "confirmation_required",
    "infeasible_goal",
    "scope_boundary",
}

VALID_OUTCOMES = {"success", "failed", "refused"}
VALID_DIFFICULTIES = {"low", "medium", "hard"}

METRIC_KEYS = {
    "task_completion",
    "planning_quality",
    "tool_selection_accuracy",
    "verification_accuracy",
    "recovery_effectiveness",
    "evidence_accuracy",
    "execution_time",
}

REQUIRED_FIELDS = {
    "scenario_id",
    "name",
    "category",
    "difficulty",
    "research_objectives",
    "research_questions",
    "user_input",
    "expected_intent",
    "expected_workflow",
    "expected_plan",
    "required_tools",
    "required_documents",
    "expected_outcome",
    "expected_output_criteria",
    "failure_conditions",
    "evaluation_criteria",
    "adversarial_notes",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_suite_exists_and_is_large_enough():
    assert SCENARIO_DIR.is_dir()
    assert len(SCENARIO_FILES) >= 15, (
        f"the suite must contain at least 15 scenarios; found {len(SCENARIO_FILES)}"
    )


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_has_required_fields(path: Path):
    data = _load(path)
    missing = REQUIRED_FIELDS - set(data)
    assert not missing, f"{path.name} is missing required fields: {sorted(missing)}"


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_enumerated_values_are_valid(path: Path):
    data = _load(path)
    assert data["category"] in VALID_CATEGORIES
    assert data["expected_outcome"] in VALID_OUTCOMES
    assert data["difficulty"] in VALID_DIFFICULTIES
    assert data["scenario_id"].startswith("SC-")
    assert data["research_objectives"], "at least one objective must be mapped"
    for objective in data["research_objectives"]:
        assert objective in {f"O{i}" for i in range(1, 7)}


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_evaluation_criteria_cover_all_metrics(path: Path):
    data = _load(path)
    criteria = data["evaluation_criteria"]
    assert set(criteria) == METRIC_KEYS, (
        f"{path.name} evaluation_criteria must cover exactly the seven dependent variables; "
        f"missing={sorted(METRIC_KEYS - set(criteria))} extra={sorted(set(criteria) - METRIC_KEYS)}"
    )
    assert len(METRIC_KEYS) == 7, "the methodology defines seven dependent variables"
    for metric, text in criteria.items():
        assert isinstance(text, str) and text.strip(), f"{path.name}: {metric} is empty"


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_expected_plan_is_well_formed(path: Path):
    data = _load(path)
    plan = data["expected_plan"]
    for key in ("min_steps", "max_steps", "must_include_steps", "must_include_dependencies"):
        assert key in plan, f"{path.name}: expected_plan missing {key}"
    assert plan["min_steps"] <= plan["max_steps"], f"{path.name}: min_steps > max_steps"
    assert isinstance(plan["must_include_steps"], list)


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_has_adversarial_notes(path: Path):
    """Every scenario must document how the hybrid design can fail it."""
    data = _load(path)
    notes = data["adversarial_notes"]
    assert isinstance(notes, str) and len(notes.strip()) > 40, (
        f"{path.name}: adversarial_notes must be a substantive explanation of how the "
        f"hybrid architecture could fail this scenario"
    )


@pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda p: p.stem)
def test_scenario_has_failure_conditions(path: Path):
    data = _load(path)
    assert len(data["failure_conditions"]) >= 2, (
        f"{path.name}: at least two concrete failure conditions are required"
    )


def test_scenario_ids_are_unique():
    ids = [_load(p)["scenario_id"] for p in SCENARIO_FILES]
    assert len(ids) == len(set(ids)), "scenario_id values must be unique"


def test_scenario_ids_match_filenames():
    for path in SCENARIO_FILES:
        scenario_id = _load(path)["scenario_id"]
        assert path.stem.startswith(scenario_id), (
            f"{path.name} does not begin with its scenario_id {scenario_id}"
        )


def test_required_categories_are_covered():
    """All fifteen required scenario categories must be represented."""
    categories = {_load(p)["category"] for p in SCENARIO_FILES}
    required = {
        "simple_task",
        "multi_step",
        "dependency_ordering",
        "document_grounded",
        "insufficient_evidence",
        "data_analysis",
        "invalid_input",
        "unknown_tool",
        "tool_execution_failure",
        "transient_failure",
        "permanent_failure",
        "verification_failure",
        "recovery_and_replanning",
        "ambiguous_goal",
        "confirmation_required",
    }
    assert required <= categories, f"uncovered categories: {sorted(required - categories)}"


def test_scenarios_cover_both_success_and_non_success_outcomes():
    outcomes = {_load(p)["expected_outcome"] for p in SCENARIO_FILES}
    assert "success" in outcomes
    assert "refused" in outcomes
    assert "failed" in outcomes


def test_fault_injection_scenarios_are_present():
    """Recovery and verification scenarios must actually inject a fault."""
    faulted = [_load(p) for p in SCENARIO_FILES if "fault_injection" in _load(p)]
    assert len(faulted) >= 4
    modes = {f["fault_injection"]["mode"] for f in faulted}
    assert len(modes) >= 4, f"fault modes should be diverse, found {sorted(modes)}"


def test_referenced_documents_exist():
    """Every referenced corpus file must exist in the repository."""
    for path in SCENARIO_FILES:
        data = _load(path)
        for doc in data["required_documents"]:
            assert (REPO_ROOT / doc).exists(), f"{path.name} references missing document: {doc}"


def test_ground_truth_present_for_computable_scenarios():
    """Scenarios with computable answers must carry their ground truth."""
    for path in SCENARIO_FILES:
        data = _load(path)
        if data["category"] in {"data_analysis", "document_grounded"}:
            assert "ground_truth" in data, (
                f"{path.name} is a computable scenario and must record ground_truth"
            )


def test_scenarios_do_not_predetermine_the_winner():
    """No scenario may assert that the hybrid condition wins."""
    for path in SCENARIO_FILES:
        data = _load(path)
        blob = json.dumps(data).lower()
        for phrase in ("hybrid outperforms", "hybrid will win", "hybrid beats"):
            assert phrase not in blob, (
                f"{path.name} appears to pre-determine the outcome of the experiment"
            )
