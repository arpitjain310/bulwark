import pytest

from orchestrator.spec import load_spec

VALID = """
version: 1
resources:
  - {name: network, type: vpc}
  - {name: db, type: postgres, depends_on: [network]}
"""


def test_loads_valid_spec():
    spec = load_spec(VALID)
    assert [r.name for r in spec.resources] == ["network", "db"]


def test_rejects_duplicate_names():
    with pytest.raises(ValueError, match="duplicate"):
        load_spec("resources: [{name: a, type: t}, {name: a, type: t}]")


def test_rejects_unknown_dependency():
    with pytest.raises(ValueError, match="unknown"):
        load_spec("resources: [{name: a, type: t, depends_on: [ghost]}]")


def test_rejects_cycle():
    with pytest.raises(ValueError, match="cycle"):
        load_spec(
            "resources: ["
            "{name: a, type: t, depends_on: [b]}, "
            "{name: b, type: t, depends_on: [a]}]"
        )


def test_rejects_invalid_protection():
    with pytest.raises(ValueError):
        load_spec("resources: [{name: a, type: t, protection: super}]")


def test_rejects_unknown_field():
    # The old durable/protected booleans are now removed; a stale spec fails loudly
    # instead of being ignored.
    with pytest.raises(ValueError):
        load_spec("resources: [{name: a, type: t, durable: true}]")
