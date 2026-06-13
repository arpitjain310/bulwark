"""In-memory mock provider.

Lets the whole engine — including the rollback/teardown paths — be developed and
tested without cloud cost. Supports fault injection so partial-failure paths are
deterministic.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..provider import Provider, ResourceState
from ..spec import Resource


class MockProvider(Provider):
    def __init__(self, sidecar: Path | None = None) -> None:
        # With a sidecar parameter the mock persists to JSON, so a CLI
        # re-apply sees the resources a previous run created. Without one it is 
        # in-memory.
        self._sidecar = Path(sidecar) if sidecar else None
        self._store: dict[str, ResourceState] = {}
        # name -> exception to raise on create/delete, for partial-failure tests.
        self._fail_on_create: dict[str, Exception] = {}
        self._fail_on_delete: dict[str, Exception] = {}
        self._created: list[str] = []
        self._deleted: list[str] = []
        if self._sidecar and self._sidecar.exists():
            raw = json.loads(self._sidecar.read_text())
            self._store = {name: ResourceState(**data) for name, data in raw.items()}

    def fail_create(self, name: str, exc: Exception | None = None) -> None:
        """Arrange for create(name) to raise, simulating a partial failure."""
        self._fail_on_create[name] = exc or RuntimeError(f"injected create failure: {name}")

    def fail_delete(self, name: str, exc: Exception | None = None) -> None:
        """Arrange for delete(name) to raise, simulating a delete that may not
        have landed — the case a resumable rollback must handle."""
        self._fail_on_delete[name] = exc or RuntimeError(f"injected delete failure: {name}")

    def heal(self) -> None:
        """Clear injected faults, simulating a transient failure resolving."""
        self._fail_on_create.clear()
        self._fail_on_delete.clear()

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
        self._created.append(resource.name)
        self._save()
        return state

    def delete(self, state: ResourceState) -> None:
        if state.name in self._fail_on_delete:
            raise self._fail_on_delete[state.name]
        self._store.pop(state.name, None)  # idempotent: safe to re-delete
        self._deleted.append(state.name)
        self._save()

    def _save(self) -> None:
        if self._sidecar:
            data = {name: asdict(state) for name, state in self._store.items()}
            self._sidecar.write_text(json.dumps(data, indent=2, sort_keys=True))

    def live(self) -> list[str]:
        """Test/inspection helper: names of currently-live resources."""
        return sorted(self._store)

    def creations(self) -> list[str]:
        """Test/inspection helper: names created, in call order."""
        return list(self._created)

    def deletions(self) -> list[str]:
        """Test/inspection helper: names deleted, in call order."""
        return list(self._deleted)
