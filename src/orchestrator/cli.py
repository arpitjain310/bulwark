"""Thin CLI driver over the orchestration engine."""
from __future__ import annotations

import argparse
from pathlib import Path

from .engine import Orchestrator
from .providers.mock import MockProvider
from .rollback import RollbackEngine, RollbackError
from .spec import Spec, load_spec
from .state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrate")
    parser.add_argument("command", choices=["apply", "teardown"])
    parser.add_argument("spec", type=Path, help="path to a YAML spec")
    parser.add_argument("--state", type=Path, default=Path(".orchestrator-state.json"))
    parser.add_argument(
        "--simulate-failure",
        metavar="NAME",
        help="it inject a create failure at NAME to demonstrate rollback",
    )
    args = parser.parse_args(argv)

    spec = load_spec(args.spec.read_text())
    provider = MockProvider()  # TODO: select real provider via flag
    if args.simulate_failure:
        provider.fail_create(args.simulate_failure)
    store = StateStore(args.state)

    if args.command == "apply":
        return _apply(provider, store, spec)
    return _teardown(provider, store, spec)


def _apply(provider: MockProvider, store: StateStore, spec: Spec) -> int:
    try:
        states = Orchestrator(provider, store).apply(spec)
    except RollbackError as exc:
        print(f"apply failed AND rollback was incomplete: {exc}")
        print(f"  still live (needs attention): {provider.live()}")
        return 2
    except Exception as exc:
        print(f"apply failed: {exc}")
        print(f"  rolled back — torn down: {provider.deletions()}; preserved: {provider.live()}")
        return 1
    print(f"applied {len(states)} resources: {[s.name for s in states]}")
    return 0


def _teardown(provider: MockProvider, store: StateStore, spec: Spec) -> int:
    try:
        RollbackEngine(provider, store).teardown(spec)
    except Exception as exc:
        print(f"teardown refused: {exc}")
        return 1
    print("torn down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
