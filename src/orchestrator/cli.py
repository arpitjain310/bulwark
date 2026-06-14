"""Thin CLI driver over the orchestration engine."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .engine import Orchestrator
from .provider import Provider
from .providers.fault import FaultInjectingProvider
from .providers.mock import MockProvider
from .rollback import RollbackEngine, RollbackError
from .spec import Spec, load_spec
from .state import StateStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrate")
    parser.add_argument("command", choices=["apply", "teardown"])
    parser.add_argument("spec", type=Path, help="path to a YAML spec")
    parser.add_argument("--state", type=Path, default=Path(".orchestrator-state.json"))
    parser.add_argument("--provider", choices=["mock", "aws", "local"], default="mock")
    parser.add_argument("--region", default="us-east-1", help="AWS region for --provider aws")
    parser.add_argument(
        "--root", type=Path, default=Path(".bulwark-local"),
        help="base directory for --provider local",
    )
    parser.add_argument(
        "--simulate-failure",
        metavar="NAME",
        help="inject a create failure at NAME to demonstrate rollback",
    )
    args = parser.parse_args(argv)

    _configure_logging()
    spec = load_spec(args.spec.read_text())
    provider = _build_provider(args)
    store = StateStore(args.state)

    if args.command == "apply":
        return _apply(provider, store, spec)
    return _teardown(provider, store, spec)


def _build_provider(args: argparse.Namespace) -> Provider:
    provider = _base_provider(args)
    if args.simulate_failure:
        provider = FaultInjectingProvider(provider, {args.simulate_failure})
    return provider


def _base_provider(args: argparse.Namespace) -> Provider:
    if args.provider == "aws":
        from .providers.real import AwsProvider  # lazy import keeps boto3 optional

        return AwsProvider(region=args.region)
    if args.provider == "local":
        from .providers.local import LocalFilesystemProvider

        return LocalFilesystemProvider(root=args.root)
    # Sidecar next to the state file so re-apply sees earlier runs' resources.
    return MockProvider(sidecar=args.state.with_suffix(".mock.json"))


def _apply(provider: Provider, store: StateStore, spec: Spec) -> int:
    try:
        states = Orchestrator(provider, store).apply(spec)
    except RollbackError as exc:
        print(f"apply failed; rollback incomplete: {exc}")
        return 2
    except Exception as exc:
        print(f"apply failed: {exc} (rolled back; see lifecycle log)")
        return 1
    print(f"applied {len(states)} resources: {[s.name for s in states]}")
    return 0


def _teardown(provider: Provider, store: StateStore, spec: Spec) -> int:
    try:
        RollbackEngine(provider, store).teardown(spec)
    except Exception as exc:
        print(f"teardown refused: {exc}")
        return 1
    print("torn down")
    return 0


def _configure_logging() -> None:
    """Print lifecycle events to stderr."""
    log = logging.getLogger("bulwark")
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)


if __name__ == "__main__":
    raise SystemExit(main())
