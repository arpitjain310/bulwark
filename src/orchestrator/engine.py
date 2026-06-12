"""Core orchestration loop: reconcile reality to a Spec.

Apply creates resources in dependency order, idempotently. On partial failure it
hands off to the rollback engine, which tears down this run's ephemeral resources
while preserving durable ones.
"""
from __future__ import annotations

from .graph import topological_order
from .provider import Provider, ResourceState
from .rollback import RollbackEngine
from .spec import Spec
from .state import StateStore


class Orchestrator:
    def __init__(self, provider: Provider, store: StateStore) -> None:
        self.provider = provider
        self.store = store

    def apply(self, spec: Spec) -> list[ResourceState]:
        """Create/reconcile every resource in dependency order, idempotently.

        Returns the resulting live states. On failure, triggers rollback of
        this run's ephemeral resources and re-raises.
        """
        created_this_run: list[ResourceState] = []
        try:
            results: list[ResourceState] = []
            for resource in topological_order(spec.resources):
                existing = self.store.get(resource.name)
                if existing is not None:
                    results.append(existing)  # idempotent no-op
                    continue
                state = self.provider.create(resource)
                self.store.put(state)
                created_this_run.append(state)
                results.append(state)
            return results
        except Exception:
            RollbackEngine(self.provider, self.store).rollback(spec, created_this_run)
            raise
