from orchestrator.engine import Orchestrator
from orchestrator.providers.mock import MockProvider
from orchestrator.spec import load_spec
from orchestrator.state import StateStore

SPEC = """
resources:
  - {name: net, type: vpc}
  - {name: app, type: service, depends_on: [net]}
"""


def test_reapply_is_noop(tmp_path):
    provider = MockProvider()
    store = StateStore(tmp_path / "state.json")
    orch = Orchestrator(provider, store)
    spec = load_spec(SPEC)

    first = orch.apply(spec)
    assert sorted(s.name for s in first) == ["app", "net"]
    assert provider.live() == ["app", "net"]

    # Second apply: reality already matches the spec -> nothing new created.
    before = dict(provider._store)
    orch.apply(spec)
    assert provider._store == before
