import pytest

from orchestrator.engine import Orchestrator
from orchestrator.providers.mock import MockProvider
from orchestrator.rollback import ProtectedResourceError, RollbackEngine
from orchestrator.spec import load_spec
from orchestrator.state import StateStore

SPEC = """
resources:
  - {name: net, type: vpc, durable: true}
  - {name: db, type: postgres, depends_on: [net], protected: true}
  - {name: cache, type: redis, depends_on: [net]}
  - {name: app, type: service, depends_on: [db, cache]}
"""


def test_rollback_preserves_durable_and_protected(tmp_path):
    provider = MockProvider()
    provider.fail_create("app")  # partial failure on the last resource
    store = StateStore(tmp_path / "s.json")
    spec = load_spec(SPEC)

    with pytest.raises(RuntimeError):
        Orchestrator(provider, store).apply(spec)

    live = provider.live()
    assert "cache" not in live   # ephemeral resource torn down
    assert "net" in live         # durable resource preserved
    assert "db" in live          # protected resource preserved
    assert "app" not in live     # never created


def test_teardown_refuses_protected(tmp_path):
    provider = MockProvider()
    store = StateStore(tmp_path / "s.json")
    spec = load_spec(SPEC)
    Orchestrator(provider, store).apply(spec)

    with pytest.raises(ProtectedResourceError):
        RollbackEngine(provider, store).teardown(spec)


@pytest.mark.skip(reason="resumable reverse-topological state machine not built yet")
def test_rollback_is_resumable_after_a_failed_delete():
    """A rollback that itself fails partway must converge on re-run."""
