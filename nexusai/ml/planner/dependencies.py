"""Dependency graph construction and resolution for structured plans.

Uses NetworkX for graph construction, cycle detection and topological
ordering. The planner does not execute tasks; this module only reasons
about the structure of a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx


@dataclass
class DependencyReport:
    """Outcome of resolving a dependency graph.

    Attributes:
        is_valid: True when the graph has no structural defects.
        errors: Human-readable descriptions of every structural defect.
        execution_order: Topologically ordered task ids (empty if invalid).
        parallel_levels: Groups of task ids that may run concurrently.
        missing_dependencies: References to task ids that do not exist.
        self_dependencies: Task ids that depend on themselves.
        duplicate_task_ids: Task ids appearing more than once.
        cycles: Task ids that participate in a dependency cycle.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    parallel_levels: list[list[str]] = field(default_factory=list)
    missing_dependencies: list[str] = field(default_factory=list)
    self_dependencies: list[str] = field(default_factory=list)
    duplicate_task_ids: list[str] = field(default_factory=list)
    cycles: list[str] = field(default_factory=list)


def build_dependency_graph(
    task_ids: list[str],
    dependencies: list[tuple[str, str]],
) -> nx.DiGraph:
    """Build a directed graph of task dependencies.

    Args:
        task_ids: All task ids in the plan.
        dependencies: Pairs of (prerequisite_id, dependent_id). The
            prerequisite must run before the dependent.

    Returns:
        A directed graph with one node per task id.
    """
    graph = nx.DiGraph()
    for task_id in task_ids:
        graph.add_node(task_id)
    for prerequisite, dependent in dependencies:
        # Edges to unknown nodes are added so that they can be reported;
        # they are removed again by the validation step.
        graph.add_edge(prerequisite, dependent)
    return graph


def find_duplicate_task_ids(task_ids: list[str]) -> list[str]:
    """Return task ids that appear more than once, preserving order."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for task_id in task_ids:
        if task_id in seen and task_id not in duplicates:
            duplicates.append(task_id)
        seen.add(task_id)
    return duplicates


def resolve_dependencies(
    task_ids: list[str],
    dependencies: list[tuple[str, str]],
) -> DependencyReport:
    """Resolve a dependency graph into a validated execution order.

    Detects duplicate task ids, missing dependency references, self
    dependencies and cycles, and computes both a total execution order and
    the parallel execution levels.

    Args:
        task_ids: All task ids in the plan.
        dependencies: Pairs of (prerequisite_id, dependent_id).

    Returns:
        A :class:`DependencyReport` describing the outcome.
    """
    errors: list[str] = []
    known_ids = set(task_ids)

    # --- duplicate task ids -------------------------------------------------
    duplicate_task_ids = find_duplicate_task_ids(task_ids)
    for duplicate in duplicate_task_ids:
        errors.append(f"Duplicate task id: {duplicate}")

    # --- missing dependency references --------------------------------------
    missing_dependencies: list[str] = []
    for prerequisite, dependent in dependencies:
        for referenced in (prerequisite, dependent):
            if referenced not in known_ids and referenced not in missing_dependencies:
                missing_dependencies.append(referenced)
    for referenced in missing_dependencies:
        errors.append(f"Dependency references unknown task: {referenced}")

    # --- self dependencies --------------------------------------------------
    self_dependencies: list[str] = []
    for prerequisite, dependent in dependencies:
        if prerequisite == dependent and prerequisite not in self_dependencies:
            self_dependencies.append(prerequisite)
    for task_id in self_dependencies:
        errors.append(f"Self-dependency detected: {task_id}")

    # --- build a graph restricted to known tasks ----------------------------
    graph = build_dependency_graph(sorted(known_ids), [])
    for prerequisite, dependent in dependencies:
        if prerequisite in known_ids and dependent in known_ids and prerequisite != dependent:
            graph.add_edge(prerequisite, dependent)

    # --- cycle detection ----------------------------------------------------
    # `cycle_basis` is undirected-only; a directed cycle is found with
    # `simple_cycles`, which enumerates the elementary directed cycles.
    cycles: list[str] = []
    try:
        for cycle in nx.simple_cycles(graph):
            for node in cycle:
                if node not in cycles:
                    cycles.append(node)
    except nx.NetworkXNoCycle:  # pragma: no cover - networkx internal guard
        cycles = []
    if cycles:
        errors.append(f"Cyclic dependency detected involving: {', '.join(sorted(cycles))}")

    # --- topological ordering ----------------------------------------------
    execution_order: list[str] = []
    parallel_levels: list[list[str]] = []
    if not errors:
        try:
            execution_order = list(nx.lexicographical_topological_sort(graph))
        except nx.NetworkXUnfeasible:  # pragma: no cover - guarded by cycle check
            errors.append("Cyclic dependency detected")
        else:
            parallel_levels = compute_parallel_levels(graph)

    return DependencyReport(
        is_valid=not errors,
        errors=errors,
        execution_order=execution_order,
        parallel_levels=parallel_levels,
        missing_dependencies=missing_dependencies,
        self_dependencies=self_dependencies,
        duplicate_task_ids=duplicate_task_ids,
        cycles=cycles,
    )


def compute_parallel_levels(graph: nx.DiGraph) -> list[list[str]]:
    """Group tasks into levels that may be executed concurrently.

    Tasks in the same level have no dependency relationship with each other.
    A future execution phase may run a level in parallel; Day 3 does not
    execute anything.

    Args:
        graph: The dependency graph.

    Returns:
        A list of levels, each a list of task ids.
    """
    if graph.number_of_nodes() == 0:
        return []

    levels: list[list[str]] = []
    remaining = set(graph.nodes)
    resolved: set[str] = set()

    while remaining:
        ready = sorted(
            node
            for node in remaining
            if all(
                predecessor in resolved or predecessor not in remaining
                for predecessor in graph.predecessors(node)
            )
        )
        if not ready:
            # Cycle: remaining nodes cannot be levelled.
            levels.append(sorted(remaining))
            break
        levels.append(ready)
        resolved.update(ready)
        remaining -= set(ready)

    return levels


def find_independent_tasks(
    task_ids: list[str],
    dependencies: list[tuple[str, str]],
) -> list[list[str]]:
    """Return groups of tasks that could potentially execute in parallel."""
    graph = build_dependency_graph(sorted(set(task_ids)), [])
    known = set(task_ids)
    for prerequisite, dependent in dependencies:
        if prerequisite in known and dependent in known and prerequisite != dependent:
            graph.add_edge(prerequisite, dependent)
    return compute_parallel_levels(graph)
