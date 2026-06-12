"""Dependency-graph ordering, shared by apply and rollback."""
from __future__ import annotations

from .spec import Resource


def topological_order(resources: list[Resource]) -> list[Resource]:
    """Resources ordered so every dependency precedes its dependents.

    Assumes the graph is acyclic (the spec validator rejects cycles).
    """
    by_name = {r.name: r for r in resources}
    ordered: list[Resource] = []
    seen: set[str] = set()

    def visit(r: Resource) -> None:
        if r.name in seen:
            return
        for dep in r.depends_on:
            visit(by_name[dep])
        seen.add(r.name)
        ordered.append(r)

    for r in resources:
        visit(r)
    return ordered
