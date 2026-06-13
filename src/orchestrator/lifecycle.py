"""Structured lifecycle logging

The engine and rollback emit an event whenever a resource changes state, so a run
leaves a machine-readable trail (resource, action, status, duration). Events go to
the `bulwark` logger; the CLI prints them, the test suite captures them, and by
default they're silent.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger("bulwark")


def emit(resource: str, action: str, *, status: str = "ok", duration_ms: float | None = None) -> None:
    """Log one lifecycle event as a JSON line."""
    event = {"resource": resource, "action": action, "status": status}
    if duration_ms is not None:
        event["duration_ms"] = round(duration_ms, 1)
    logger.info(json.dumps(event))
