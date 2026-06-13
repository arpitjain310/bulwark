import pytest

from orchestrator.engine import Orchestrator
from orchestrator.providers.mock import MockProvider
from orchestrator.rollback import Phase, ProtectedResourceError, RollbackEngine, RollbackError
from orchestrator.spec import load_spec
from orchestrator.state import StateStore

SPEC = """
resources:
  - {name: net, type: vpc, protection: durable}
  - {name: db, type: postgres, depends_on: [net], protection: protected}
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


def test_teardown_refuses_protected_before_any_delete(tmp_path):
    provider = MockProvider()
    store = StateStore(tmp_path / "s.json")
    spec = load_spec(SPEC)
    Orchestrator(provider, store).apply(spec)

    with pytest.raises(ProtectedResourceError):
        RollbackEngine(provider, store).teardown(spec)
    assert provider.deletions() == []  # aborted before touching anything


def test_teardown_deletes_durable_unlike_rollback(tmp_path):
    # No protected resource, so teardown proceeds — and removes the durable one,
    # which a rollback would have kept. That difference is the whole point.
    spec_text = """
resources:
  - {name: net, type: vpc, protection: durable}
  - {name: app, type: service, depends_on: [net]}
"""
    provider = MockProvider()
    store = StateStore(tmp_path / "s.json")
    spec = load_spec(spec_text)
    Orchestrator(provider, store).apply(spec)

    phases = RollbackEngine(provider, store).teardown(spec)

    assert provider.live() == []                    # durable 'net' is gone too
    assert provider.deletions() == ["app", "net"]   # reverse-topological
    assert phases["net"] == Phase.DELETED


def test_rollback_deletes_dependents_before_dependencies(tmp_path):
    spec_text = """
resources:
  - {name: net, type: vpc}
  - {name: app, type: service, depends_on: [net]}
  - {name: lb, type: lb, depends_on: [app]}
"""
    provider = MockProvider()
    provider.fail_create("lb")  # fail after net + app are created
    store = StateStore(tmp_path / "s.json")
    spec = load_spec(spec_text)

    with pytest.raises(RuntimeError):
        Orchestrator(provider, store).apply(spec)

    # Reverse-topological: the dependent (app) is torn down before its
    # dependency (net), regardless of creation order.
    assert provider.deletions() == ["app", "net"]


def test_rollback_is_resumable_after_a_failed_delete(tmp_path):
    """A rollback that itself fails partway converges on re-run from disk."""
    statepath = tmp_path / "s.json"
    spec = load_spec(SPEC)
    provider = MockProvider()
    provider.fail_create("app")    # apply fails at the last resource
    provider.fail_delete("cache")  # rollback can't delete the ephemeral
    store = StateStore(statepath)

    with pytest.raises(RollbackError):
        Orchestrator(provider, store).apply(spec)

    assert "cache" in provider.live()  # the failed delete left it behind

    # Resume as if in a fresh process: the transient fault clears, and a new
    # StateStore reads the rollback journal back from disk.
    provider.heal()
    resumed = StateStore(statepath)
    phases = RollbackEngine(provider, resumed).rollback(spec)

    assert phases["cache"] == Phase.DELETED
    assert "cache" not in provider.live()  # converged
    assert "net" in provider.live()        # durable preserved
    assert "db" in provider.live()         # protected preserved
    assert StateStore(statepath).rollback_targets() is None  # journal cleared
