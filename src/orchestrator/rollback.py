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
from .spec import Protection, Spec
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


class DeletionError(RuntimeError):
    """A bulk delete finished with one or more resources left undeleted.

    Carries the per-resource failures and the final phase of every resource.
    """

    def __init__(self, failures: dict[str, Exception], phases: dict[str, Phase]) -> None:
        self.failures = failures
        self.phases = phases
        super().__init__("undeleted: " + ", ".join(sorted(failures)))


class RollbackError(DeletionError):
    """Rollback left resources undeleted; the triggering apply error is the cause."""


class TeardownError(DeletionError):
    """Teardown left resources undeleted."""


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
        to_delete: list[str] = []
        for res in order:
            if res.protection is not Protection.EPHEMERAL:
                phases[res.name] = Phase.PRESERVED  # durable and protected both survives
            else:
                to_delete.append(res.name)

        del_phases, failures = self._delete_each(to_delete)
        phases.update(del_phases)
        if failures:
            raise RollbackError(failures, phases)
        self.store.end_rollback()
        return phases

    def _delete_each(
        self, names: list[str]
    ) -> tuple[dict[str, Phase], dict[str, Exception]]:
        """Delete the given resources in order.

        A failed delete is recorded and the rest still run. Deletes must be
        idempotent: a name already gone counts as deleted.
        """
        phases: dict[str, Phase] = {}
        failures: dict[str, Exception] = {}
        for name in names:
            state = self.store.get(name)
            if state is None:
                phases[name] = Phase.DELETED  # already gone
                continue
            phases[name] = Phase.DELETING
            try:
                self.provider.delete(state)
            except Exception as exc:
                # Record and keep going; a stuck resource must not block the rest.
                phases[name] = Phase.FAILED
                failures[name] = exc
                continue
            self.store.forget(name)
            phases[name] = Phase.DELETED
        return phases, failures

    def teardown(self, spec: Spec) -> dict[str, Phase]:
        """Destroy the whole stack in reverse-topological order.

        Teardown is an explicit destroy, so it removes durable resources too —
        the ones a rollback would keep. But a single protected resource makes it
        refuse the entire run before deleting anything. Similar in the way a Terraform's
        prevent_destroy aborts a plan.
        """
        by_name = {r.name: r for r in spec.resources}
        managed = {s.name for s in self.store.all()}

        # One protected resource aborts the run before any delete.
        for name in sorted(managed):
            res = by_name.get(name)
            if res is not None and res.protection is Protection.PROTECTED:
                raise ProtectedResourceError(f"refusing to tear down protected resource '{name}'")

        order = [r.name for r in reversed(topological_order(spec.resources)) if r.name in managed]
        phases, failures = self._delete_each(order)
        if failures:
            raise TeardownError(failures, phases)
        return phases
