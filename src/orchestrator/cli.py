"""Thin CLI driver over the orchestration engine."""
from __future__ import annotations

import argparse
from pathlib import Path

from .engine import Orchestrator
from .providers.mock import MockProvider
from .rollback import RollbackEngine
from .spec import load_spec
from .state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrate")
    parser.add_argument("command", choices=["apply", "teardown"])
    parser.add_argument("spec", type=Path, help="path to a YAML spec")
    parser.add_argument("--state", type=Path, default=Path(".orchestrator-state.json"))
    args = parser.parse_args(argv)

    spec = load_spec(args.spec.read_text())
    provider = MockProvider()  # TODO: select real provider via flag
    store = StateStore(args.state)

    if args.command == "apply":
        states = Orchestrator(provider, store).apply(spec)
        print(f"applied {len(states)} resources: {[s.name for s in states]}")
    else:
        RollbackEngine(provider, store).teardown(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
