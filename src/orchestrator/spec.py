"""Declarative spec format: parse and validate, rejecting bad input loudly.

A spec describes a desired multi-resource stack. Each resource declares how
disposable it is, which is what a rollback consults:
  - ephemeral (default): safe to tear down on partial failure
  - durable:             preserved across rollbacks
  - protected:           structurally un-deletable
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Resource(BaseModel):
    name: str
    type: str
    # Inputs handed to the provider; opaque to the engine.
    config: dict = Field(default_factory=dict)
    # Names of resources that must exist before this one (creation order).
    depends_on: list[str] = Field(default_factory=list)
    durable: bool = False
    protected: bool = False


class Spec(BaseModel):
    version: int = 1
    resources: list[Resource]

    @model_validator(mode="after")
    def _validate(self) -> "Spec":
        names = [r.name for r in self.resources]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"duplicate resource names: {dupes}")
        known = set(names)
        for r in self.resources:
            unknown = [d for d in r.depends_on if d not in known]
            if unknown:
                raise ValueError(f"resource '{r.name}' depends on unknown: {unknown}")
        _reject_cycles(self.resources)
        return self


def _reject_cycles(resources: list[Resource]) -> None:
    graph = {r.name: r.depends_on for r in resources}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}

    def visit(n: str, stack: list[str]) -> None:
        color[n] = GRAY
        for dep in graph[n]:
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise ValueError(f"dependency cycle: {' -> '.join(cycle)}")
            if color[dep] == WHITE:
                visit(dep, stack + [dep])
        color[n] = BLACK

    for n in graph:
        if color[n] == WHITE:
            visit(n, [n])


def load_spec(text: str) -> Spec:
    """Parse YAML text into a validated Spec. Raises ValueError on bad input."""
    import yaml

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("spec must be a mapping at the top level")
    return Spec.model_validate(data)
