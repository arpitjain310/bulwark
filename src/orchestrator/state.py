"""State store: what's been created (so re-runs are no-ops) plus a rollback
journal (so an interrupted rollback can resume from disk).

A simple JSON-file store.
"""
from __future__ import annotations

import json
from pathlib import Path

from .provider import ResourceState


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._resources: dict[str, dict] = {}
        self._rollback: dict | None = None
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if "resources" in data or "rollback" in data:
                self._resources = data.get("resources", {})
                self._rollback = data.get("rollback")
            else:  # {name: state} format
                self._resources = data

    # --- resource state --------------------------------------------------
    def get(self, name: str) -> ResourceState | None:
        raw = self._resources.get(name)
        return ResourceState(**raw) if raw else None

    def put(self, state: ResourceState) -> None:
        self._resources[state.name] = {
            "name": state.name,
            "type": state.type,
            "external_id": state.external_id,
            "attributes": state.attributes,
        }
        self._flush()

    def forget(self, name: str) -> None:
        self._resources.pop(name, None)
        self._flush()

    def all(self) -> list[ResourceState]:
        return [ResourceState(**raw) for raw in self._resources.values()]

    # --- rollback ------------------------------------------------
    def begin_rollback(self, target_names: list[str]) -> None:
        """Record which resources a rollback owns, so it can resume."""
        self._rollback = {"targets": sorted(target_names)}
        self._flush()

    def rollback_targets(self) -> list[str] | None:
        """Targets of an in-progress rollback, or None if none is open."""
        return list(self._rollback["targets"]) if self._rollback else None

    def end_rollback(self) -> None:
        self._rollback = None
        self._flush()

    def _flush(self) -> None:
        data: dict = {"resources": self._resources}
        if self._rollback is not None:
            data["rollback"] = self._rollback
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))
