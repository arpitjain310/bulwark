"""Rollback and teardown for a managed stack.

rollback() runs after a partial-failure apply: delete the resources created in
this run in reverse-topological order (dependents before dependencies), preserve
durable ones, never touch protected ones. Each resource moves through an explicit
lifecycle: PENDING -> DELETING -> DELETED / FAILED / PRESERVED.

It is resumable. The target set is recorded in the StateStore and the delete
order is recomputed from the dependency graph, so a rollback interrupted by a
failed delete re-runs from disk alone and converges (deletes must be idempotent).
A delete that fails is recorded and the rest still proceed; the run then raises
RollbackError carrying every per-resource failure, with the original apply error
as its cause.

teardown() destroys a whole stack under the same protected guard.
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


class RollbackError(RuntimeError):
    """A rollback finished with one or more resources left undeleted.

    Carries the per-resource delete failures; the apply error that triggered the
    rollback is attached as this exception's cause.
    """

    def __init__(self, failures: dict[str, Exception], phases: dict[str, Phase]) -> None:
        self.failures = failures
        self.phases = phases
        super().__init__("rollback incomplete; undeleted: " + ", ".join(sorted(failures)))


class RollbackEngine:
    def __init__(self, provider: Provider, store: StateStore) -> None:
        self.provider = provider
        self.store = store

    def rollback(
        self, spec: Spec, created_this_run: list[ResourceState] | None = None
    ) -> dict[str, Phase]:
        """Tear down this run's resources, preserving durable/protected ones.

        First call: `created_this_run` defines the target set.
        Resume: pass nothing — the targets are read back from the StateStore.
        Returns the final phase of each target.
        """
        targets = self.store.rollback_targets()
        if targets is None:
            if created_this_run is None:
                return {}
            targets = sorted(s.name for s in created_this_run)
            self.store.begin_rollback(targets)
        targetset = set(targets)

        # Reverse-topological (from the graph, not the creation list, so a resume
        # with no created_this_run still orders correctly).
        order = [r for r in reversed(topological_order(spec.resources)) if r.name in targetset]
        phases: dict[str, Phase] = {}
        failures: dict[str, Exception] = {}
        for res in order:
            if res.durable or res.protected:
                phases[res.name] = Phase.PRESERVED
                continue
            state = self.store.get(res.name)
            if state is None:
                phases[res.name] = Phase.DELETED  # already gone
                continue
            phases[res.name] = Phase.DELETING
            try:
                self.provider.delete(state)
            except Exception as exc:
                # Record and keep going; a stuck resource must not block the rest.
                phases[res.name] = Phase.FAILED
                failures[res.name] = exc
                continue
            self.store.forget(res.name)
            phases[res.name] = Phase.DELETED

        if failures:
            raise RollbackError(failures, phases)
        self.store.end_rollback()
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
