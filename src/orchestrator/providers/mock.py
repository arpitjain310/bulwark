"""In-memory mock provider.

Lets the whole engine — including the rollback/teardown paths — be developed and
tested without cloud cost. Supports fault injection so partial-failure paths are
deterministic.
"""
from __future__ import annotations

from ..provider import Provider, ResourceState
from ..spec import Resource


class MockProvider(Provider):
    def __init__(self) -> None:
        self._store: dict[str, ResourceState] = {}
        # name -> exception to raise on create, for partial-failure tests.
        self._fail_on_create: dict[str, Exception] = {}

    def fail_create(self, name: str, exc: Exception | None = None) -> None:
        """Arrange for create(name) to raise, simulating a partial failure."""
        self._fail_on_create[name] = exc or RuntimeError(f"injected create failure: {name}")

    def read(self, resource: Resource) -> ResourceState | None:
        return self._store.get(resource.name)

    def create(self, resource: Resource) -> ResourceState:
        if resource.name in self._fail_on_create:
            raise self._fail_on_create[resource.name]
        existing = self._store.get(resource.name)
        if existing is not None:
            return existing  # idempotent
        state = ResourceState(
            name=resource.name,
            type=resource.type,
            external_id=f"mock://{resource.type}/{resource.name}",
            attributes=dict(resource.config),
        )
        self._store[resource.name] = state
        return state

    def delete(self, state: ResourceState) -> None:
        self._store.pop(state.name, None)

    def live(self) -> list[str]:
        """Test/inspection helper: names of currently-live resources."""
        return sorted(self._store)
