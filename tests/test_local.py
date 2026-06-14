import pytest

from orchestrator.engine import Orchestrator
from orchestrator.providers.fault import FaultInjectingProvider
from orchestrator.providers.local import LocalFilesystemProvider
from orchestrator.rollback import ProtectedResourceError, RollbackEngine
from orchestrator.spec import load_spec
from orchestrator.state import StateStore

SPEC = """
resources:
  - {name: net, type: dir, protection: durable}
  - {name: cache, type: dir, depends_on: [net]}
  - {name: app, type: dir, depends_on: [cache]}
"""


def test_local_apply_creates_dirs_and_reapply_is_noop(tmp_path):
    root = tmp_path / "world"
    provider = LocalFilesystemProvider(root)
    spec = load_spec(SPEC)

    Orchestrator(provider, StateStore(tmp_path / "s.json")).apply(spec)
    assert (root / "net" / "resource.json").exists()
    assert (root / "app" / "resource.json").exists()

    # read-before-skip: re-apply finds everything live and creates nothing
    marker = root / "app" / "resource.json"
    mtime = marker.stat().st_mtime_ns
    Orchestrator(provider, StateStore(tmp_path / "s.json")).apply(spec)
    assert marker.stat().st_mtime_ns == mtime


def test_local_rollback_preserves_durable_dir(tmp_path):
    root = tmp_path / "world"
    provider = FaultInjectingProvider(LocalFilesystemProvider(root), {"app"})
    spec = load_spec(SPEC)

    with pytest.raises(RuntimeError):
        Orchestrator(provider, StateStore(tmp_path / "s.json")).apply(spec)

    assert (root / "net").is_dir()          # durable preserved
    assert not (root / "cache").exists()    # ephemeral removed


def test_local_teardown_refuses_protected(tmp_path):
    root = tmp_path / "world"
    provider = LocalFilesystemProvider(root)
    spec = load_spec("resources: [{name: db, type: dir, protection: protected}]")
    store = StateStore(tmp_path / "s.json")
    Orchestrator(provider, store).apply(spec)

    with pytest.raises(ProtectedResourceError):
        RollbackEngine(provider, store).teardown(spec)
    assert (root / "db").is_dir()  # untouched
