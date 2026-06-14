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
    assert provider.creations() == ["net", "app"]  # created in dependency order

    # Second apply: reality already matches the spec -> nothing new created.
    orch.apply(spec)
    assert provider.creations() == ["net", "app"]  # unchanged


def test_reapply_recreates_a_resource_lost_out_of_band(tmp_path):
    provider = MockProvider()
    store = StateStore(tmp_path / "state.json")
    orch = Orchestrator(provider, store)
    spec = load_spec(SPEC)
    orch.apply(spec)

    # Drift: 'net' disappears from reality, but the state file still records it.
    net = provider.read(spec.resources[0])
    provider.delete(net)

    # Read-before-skip notices net is gone and recreates it; app is untouched.
    orch.apply(spec)
    assert provider.creations().count("net") == 2
    assert "net" in provider.live()


def test_mock_sidecar_persists_world_across_instances(tmp_path):
    sidecar = tmp_path / "world.json"
    spec = load_spec(SPEC)

    p1 = MockProvider(sidecar=sidecar)
    Orchestrator(p1, StateStore(tmp_path / "s.json")).apply(spec)
    assert p1.creations() == ["net", "app"]

    # A new provider reads the same sidecar and sees the resources, so re-apply
    # creates nothing (the CLI mock used to start empty each run).
    p2 = MockProvider(sidecar=sidecar)
    assert sorted(p2.live()) == ["app", "net"]
    Orchestrator(p2, StateStore(tmp_path / "s.json")).apply(spec)
    assert p2.creations() == []
