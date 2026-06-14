"""Provider backed by the local filesystem: each resource is a directory.

A second real backend behind the same contract — real side effects, no cloud,
and fully testable. Create, read, and delete operations are idempotent.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from ..provider import Provider, ResourceState
from ..spec import Resource


class LocalFilesystemProvider(Provider):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _marker(self, name: str) -> Path:
        return self.root / name / "resource.json"

    def read(self, resource: Resource) -> ResourceState | None:
        marker = self._marker(resource.name)
        if not marker.exists():
            return None
        return ResourceState(**json.loads(marker.read_text()))

    def create(self, resource: Resource) -> ResourceState:
        existing = self.read(resource)
        if existing is not None:
            return existing  # idempotent
        path = self.root / resource.name
        path.mkdir(parents=True, exist_ok=True)
        state = ResourceState(
            name=resource.name,
            type=resource.type,
            external_id=str(path),
            attributes=dict(resource.config),
        )
        self._marker(resource.name).write_text(json.dumps(asdict(state), indent=2))
        return state

    def delete(self, state: ResourceState) -> None:
        shutil.rmtree(self.root / state.name, ignore_errors=True)  # idempotent
