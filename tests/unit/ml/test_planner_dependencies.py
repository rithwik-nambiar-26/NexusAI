"""Tests for planner dependency graph resolution."""

from __future__ import annotations

import networkx as nx

from nexusai.ml.planner.dependencies import (
    build_dependency_graph,
    compute_parallel_levels,
    find_duplicate_task_ids,
    find_independent_tasks,
    resolve_dependencies,
)


def test_build_dependency_graph_nodes():
    """Test that every task id becomes a node."""
    graph = build_dependency_graph(["a", "b", "c"], [])
    assert set(graph.nodes) == {"a", "b", "c"}
    assert graph.number_of_edges() == 0


def test_build_dependency_graph_edges():
    """Test that dependency pairs become directed edges."""
    graph = build_dependency_graph(["a", "b"], [("a", "b")])
    assert graph.number_of_edges() == 1
    assert graph.has_edge("a", "b")
    assert not graph.has_edge("b", "a")


def test_resolve_valid_chain():
    """Test resolution of a simple valid chain."""
    report = resolve_dependencies(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert report.is_valid is True
    assert report.errors == []
    assert report.execution_order == ["a", "b", "c"]


def test_resolve_detects_duplicate_task_ids():
    """Test that duplicate task ids are reported."""
    report = resolve_dependencies(["a", "a", "b"], [("a", "b")])
    assert report.is_valid is False
    assert report.duplicate_task_ids == ["a"]
    assert any("Duplicate task id" in e for e in report.errors)


def test_find_duplicate_task_ids_preserves_order():
    """Test that duplicates are reported once, in first-seen order."""
    assert find_duplicate_task_ids(["x", "y", "x", "z", "y"]) == ["x", "y"]


def test_resolve_detects_missing_dependency():
    """Test that a dependency on an unknown task is reported."""
    report = resolve_dependencies(["a"], [("a", "ghost")])
    assert report.is_valid is False
    assert report.missing_dependencies == ["ghost"]
    assert any("unknown task: ghost" in e for e in report.errors)


def test_resolve_detects_self_dependency():
    """Test that a self dependency is reported."""
    report = resolve_dependencies(["a", "b"], [("a", "a"), ("a", "b")])
    assert report.is_valid is False
    assert report.self_dependencies == ["a"]
    assert any("Self-dependency" in e for e in report.errors)


def test_resolve_detects_two_node_cycle():
    """Test that a two node cycle is reported."""
    report = resolve_dependencies(["a", "b"], [("a", "b"), ("b", "a")])
    assert report.is_valid is False
    assert set(report.cycles) == {"a", "b"}
    assert any("Cyclic dependency" in e for e in report.errors)


def test_resolve_detects_three_node_cycle():
    """Test that a three node cycle is reported."""
    report = resolve_dependencies(
        ["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")]
    )
    assert report.is_valid is False
    assert set(report.cycles) == {"a", "b", "c"}


def test_resolve_cycle_produces_no_execution_order():
    """Test that an invalid graph yields no execution order."""
    report = resolve_dependencies(["a", "b"], [("a", "b"), ("b", "a")])
    assert report.execution_order == []
    assert report.parallel_levels == []


def test_resolve_computes_parallel_levels():
    """Test that independent tasks are grouped into a level."""
    report = resolve_dependencies(
        ["a", "b", "c", "d"], [("a", "c"), ("b", "c"), ("c", "d")]
    )
    assert report.is_valid is True
    assert report.parallel_levels == [["a", "b"], ["c"], ["d"]]


def test_resolve_execution_order_respects_dependencies():
    """Test that the execution order places prerequisites first."""
    report = resolve_dependencies(
        ["a", "b", "c"], [("c", "b"), ("b", "a")]
    )
    assert report.is_valid is True
    order = report.execution_order
    assert order.index("c") < order.index("b")
    assert order.index("b") < order.index("a")


def test_compute_parallel_levels_empty_graph():
    """Test that an empty graph produces no levels."""
    assert compute_parallel_levels(nx.DiGraph()) == []


def test_find_independent_tasks():
    """Test the public helper for parallelisable task groups."""
    levels = find_independent_tasks(
        ["a", "b", "c", "d"], [("a", "c"), ("b", "c"), ("c", "d")]
    )
    assert levels == [["a", "b"], ["c"], ["d"]]


def test_find_independent_tasks_ignores_unknown_refs():
    """Test that unknown references are ignored by the parallel helper."""
    levels = find_independent_tasks(["a"], [("a", "ghost")])
    assert levels == [["a"]]
