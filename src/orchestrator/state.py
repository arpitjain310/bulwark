"""State store: records what the orchestrator has created, so a re-run is a
no-op when reality already matches the spec.

A simple JSON-file store; the interface is what matters, not the backend.
"""
from __future__ import annotations

import json
from pathlib import Path

from .provider import ResourceState


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._state: dict[str, dict] = {}
        if self.path.exists():
            self._state = json.loads(self.path.read_text())

    def get(self, name: str) -> ResourceState | None:
        raw = self._state.get(name)
        return ResourceState(**raw) if raw else None

    def put(self, state: ResourceState) -> None:
        self._state[state.name] = {
            "name": state.name,
            "type": state.type,
            "external_id": state.external_id,
            "attributes": state.attributes,
        }
        self._flush()

    def forget(self, name: str) -> None:
        self._state.pop(name, None)
        self._flush()

    def all(self) -> list[ResourceState]:
        return [ResourceState(**raw) for raw in self._state.values()]

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2, sort_keys=True))
