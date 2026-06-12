"""Rollback and teardown for a managed stack.

rollback() runs after a partial-failure apply: delete the resources created in
this run in reverse-topological order (dependents before dependencies), preserve
durable ones, never touch protected ones. Each resource moves through an explicit
lifecycle: PENDING -> DELETING -> DELETED / FAILED / PRESERVED.

The delete order is computed from the dependency graph, not from the creation
list, so rollback can run from persisted state alone — the basis for making it
resumable next.

teardown() destroys a whole stack under the same protected guard.

Not yet resumable: a delete that fails mid-rollback re-raises rather than
persisting progress and converging on re-run.
"""
from __future__ import annotations

import enum

from .graph import topological_order
from .provider import Provider, ResourceState
from .spec import Spec
from .state import StateStore


class Phase(enum.Enum):
    """Per-resource lifecycle during a rollback."""

    PENDING = "pending"
    DELETING = "deleting"
    DELETED = "deleted"
    FAILED = "failed"
    PRESERVED = "preserved"


class ProtectedResourceError(RuntimeError):
    """Raised on any attempt to delete a protected resource."""


class RollbackEngine:
    def __init__(self, provider: Provider, store: StateStore) -> None:
        self.provider = provider
        self.store = store

    def rollback(
        self, spec: Spec, created_this_run: list[ResourceState]
    ) -> dict[str, Phase]:
        """Tear down this run's resources, preserving durable/protected ones.

        Returns the final phase of each targeted resource.
        """
        states = {s.name: s for s in created_this_run}
        targets = set(states)
        phases = {name: Phase.PENDING for name in targets}

        # Reverse-topological: dependents are deleted before their dependencies.
        order = [r for r in reversed(topological_order(spec.resources)) if r.name in targets]
        for res in order:
            if res.durable or res.protected:
                phases[res.name] = Phase.PRESERVED
                continue
            phases[res.name] = Phase.DELETING
            try:
                self.provider.delete(states[res.name])
            except Exception:
                phases[res.name] = Phase.FAILED
                raise
            phases[res.name] = Phase.DELETED
            self.store.forget(res.name)
        return phases

    def teardown(self, spec: Spec) -> None:
        """Destroy the whole stack. Protected resources are un-deletable.

        The guard runs first and unconditionally: a teardown that would touch a
        protected resource fails before deleting anything.
        """
        by_name = {r.name: r for r in spec.resources}
        for state in self.store.all():
            res = by_name.get(state.name)
            if res is not None and res.protected:
                raise ProtectedResourceError(
                    f"refusing to delete protected resource '{state.name}'"
                )
        # Reverse-topological teardown with lifecycle logging is not built yet.
        raise NotImplementedError("teardown state machine not implemented yet")
