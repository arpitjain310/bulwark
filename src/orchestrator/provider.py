"""Pluggable provider interface.

The engine speaks only this contract; backends (mock, or a real cloud resource)
implement it. Keeping the engine provider-agnostic lets the rollback/teardown
logic be developed and tested against a mock with zero cloud cost.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .spec import Resource


@dataclass(frozen=True)
class ResourceState:
    """What the provider knows about a live resource."""

    name: str
    type: str
    external_id: str
    attributes: dict


class Provider(ABC):
    """Contract every backend implements."""

    @abstractmethod
    def read(self, resource: Resource) -> ResourceState | None:
        """Return live state from the backend, or None if it doesn't exist.

        Apply calls this to reconcile: a resource that reads back is a no-op, one
        that's missing gets (re)created.
        """

    @abstractmethod
    def create(self, resource: Resource) -> ResourceState:
        """Create the resource. Must be idempotent: if it already exists and
        matches, return existing state without error."""

    @abstractmethod
    def delete(self, state: ResourceState) -> None:
        """Destroy the resource. The caller guarantees it is neither durable
        (during rollback) nor protected (ever)."""
