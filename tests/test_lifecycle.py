import json
import logging

from orchestrator.engine import Orchestrator
from orchestrator.providers.mock import MockProvider
from orchestrator.spec import load_spec
from orchestrator.state import StateStore

SPEC = """
resources:
  - {name: net, type: vpc}
  - {name: app, type: service, depends_on: [net]}
"""


def test_apply_emits_created_events_with_duration(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="bulwark")
    provider = MockProvider()
    Orchestrator(provider, StateStore(tmp_path / "s.json")).apply(load_spec(SPEC))

    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "bulwark"]
    actions = {(e["resource"], e["action"]) for e in events}
    assert ("net", "created") in actions
    assert ("app", "created") in actions
    assert all("duration_ms" in e for e in events if e["action"] == "created")
