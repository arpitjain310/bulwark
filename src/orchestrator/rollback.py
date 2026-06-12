"""Rollback and teardown for a managed stack.

rollback() runs after a partial-failure apply: delete resources created in this
run in reverse dependency order, preserve durable ones, never touch protected.
teardown() destroys a whole stack under the same protected guard.

rollback() is currently a first cut (reverse creation order). Target: an explicit
per-resource state machine (PENDING -> DELETING -> DELETED / FAILED / PRESERVED),
reverse-topological, and resumable so a rollback that fails partway can re-run and
converge.
"""
from __future__ import annotations

from .provider import Provider, ResourceState
from .spec import Spec
from .state import StateStore


class ProtectedResourceError(RuntimeError):
    """Raised on any attempt to delete a protected resource."""


class RollbackEngine:
    def __init__(self, provider: Provider, store: StateStore) -> None:
        self.provider = provider
        self.store = store

    def rollback(self, spec: Spec, created_this_run: list[ResourceState]) -> None:
        by_name = {r.name: r for r in spec.resources}
        # First cut: reverse creation order. Target: reverse-topological + resumable.
        for state in reversed(created_this_run):
            res = by_name.get(state.name)
            if res is None or res.durable or res.protected:
                continue  # preserve durable; never touch protected
            self.provider.delete(state)
            self.store.forget(state.name)

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
