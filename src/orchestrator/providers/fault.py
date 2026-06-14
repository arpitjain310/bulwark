"""Wraps any provider to fail create() at named resources.

Used by the CLI's --simulate-failure to exercise the rollback path against any
backend, so the partial-failure demo works on mock, AWS, or local alike.
"""
from __future__ import annotations

from ..provider import Provider, ResourceState
from ..spec import Resource


class FaultInjectingProvider(Provider):
    def __init__(self, inner: Provider, fail_create: set[str]) -> None:
        self._inner = inner
        self._fail_create = set(fail_create)

    def read(self, resource: Resource) -> ResourceState | None:
        return self._inner.read(resource)

    def create(self, resource: Resource) -> ResourceState:
        if resource.name in self._fail_create:
            raise RuntimeError(f"injected failure at '{resource.name}'")
        return self._inner.create(resource)

    def delete(self, state: ResourceState) -> None:
        self._inner.delete(state)
