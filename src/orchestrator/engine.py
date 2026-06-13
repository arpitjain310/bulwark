"""Core orchestration loop: reconcile reality to a Spec.

Apply creates resources in dependency order, idempotently. On partial failure it
hands off to the rollback engine, which tears down this run's ephemeral resources
while preserving durable ones.
"""
from __future__ import annotations

from .graph import topological_order
from .provider import Provider, ResourceState
from .rollback import RollbackEngine, RollbackError
from .spec import Spec
from .state import StateStore


class Orchestrator:
    def __init__(self, provider: Provider, store: StateStore) -> None:
        self.provider = provider
        self.store = store

    def apply(self, spec: Spec) -> list[ResourceState]:
        """Create/reconcile every resource in dependency order, idempotently.

        Existence is decided by reading reality, not by trusting the state file:
        a resource still live is a no-op, one that drifted away is recreated.
        Returns the resulting live states. On failure, triggers rollback of
        this run's ephemeral resources and re-raises.
        """
        created_this_run: list[ResourceState] = []
        try:
            results: list[ResourceState] = []
            for resource in topological_order(spec.resources):
                live = self.provider.read(resource)
                if live is not None:
                    if self.store.get(resource.name) is None:
                        self.store.put(live)  # adopt a resource that already existed
                    results.append(live)
                    continue
                # Not in reality (new, or drifted away since last apply) -> create.
                state = self.provider.create(resource)
                self.store.put(state)
                created_this_run.append(state)
                results.append(state)
            return results
        except Exception as apply_error:
            try:
                RollbackEngine(self.provider, self.store).rollback(spec, created_this_run)
            except RollbackError as rollback_error:
                # Cleanup itself failed: surface that, keeping the apply error as cause.
                raise rollback_error from apply_error
            raise  # clean rollback: re-raise the original apply failure
