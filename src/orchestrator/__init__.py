"""Declarative multi-resource provisioning orchestrator.

The product is the ENGINE: idempotent apply, partial-failure rollback that
separates durable from ephemeral resources, and a teardown that structurally
cannot delete protected resources.
"""
from .engine import Orchestrator, topological_order
from .provider import Provider, ResourceState
from .rollback import ProtectedResourceError, RollbackEngine
from .spec import Resource, Spec, load_spec
from .state import StateStore

__all__ = [
    "Orchestrator",
    "topological_order",
    "Provider",
    "ResourceState",
    "RollbackEngine",
    "ProtectedResourceError",
    "Resource",
    "Spec",
    "load_spec",
    "StateStore",
]
