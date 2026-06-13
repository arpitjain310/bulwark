# bulwark

[![ci](https://github.com/arpitjain310/bulwark/actions/workflows/ci.yml/badge.svg)](https://github.com/arpitjain310/bulwark/actions/workflows/ci.yml)

> Provision a multi-resource stack from a declarative spec — with idempotent
> re-runs, partial-failure rollback that preserves durable resources, and a
> teardown that *structurally cannot* delete protected resources.

**Status:** work in progress.

---

## The problem

Provisioning tooling is easy to demo and hard to make safe. The interesting
failures are not "create a resource" — they're what happens *between*
resources:

- A re-run should be a **no-op** when reality already matches the spec.
- A run that fails **halfway** must clean up after itself — but cleaning up
  blindly is how you delete a production database. Some resources are
  **durable**: created once, preserved across rollbacks. Others are
  **ephemeral**: safe to tear down.
- Some resources must be **un-deletable by construction**, not by convention.

That durable-vs-ephemeral separation — knowing precisely what a rollback is
allowed to destroy — is what this repo is about.

## What it does

```
spec.yaml ──▶ parse + validate ──▶ plan (dependency order) ──▶ apply ─┐
                                                                       │
                              ┌──── success: persist state ◀───────────┘
                              │
                              └──── partial failure ──▶ ROLLBACK
                                       tear down ephemeral created this run,
                                       PRESERVE durable, NEVER touch protected
```

- **Declarative spec** (`spec.py`) — resources, dependencies, and per-resource
  `durable` / `protected` flags. Bad input is rejected loudly (duplicate names,
  unknown dependencies, dependency cycles).
- **Pluggable provider** (`provider.py`) — the engine speaks one contract;
  backends (`MockProvider`, later one real backend) implement it.
- **Idempotent apply** (`engine.py`) — resources created in dependency order;
  re-applying skips what already exists.
- **State store** (`state.py`) — records what's been created so re-runs converge.
- **Rollback / teardown** (`rollback.py`) — on partial failure, tears down this
  run's resources in reverse dependency order, preserving durable ones and
  refusing to touch protected ones. Resumable: a rollback that fails partway
  re-runs to convergence.

## Explicit non-goals

Scope is the bottleneck, not time. This repo deliberately does **not**:

- Aim to be a Terraform/Pulumi replacement — the value is the **engine**, not
  breadth of providers.
- Manage drift detection, remote state locking, or multi-user concurrency.
- Require cloud credentials to develop or test — everything runs against a
  **mock** provider; one real backend is wired to prove the engine works against
  real infrastructure.
- Provide a config DSL beyond a small validated YAML spec.

## Rollback behaviour

- **Reverse-topological:** dependents are deleted before their dependencies.
- **Preserve by class:** durable resources survive a rollback, while protected ones are
  never touched.
- **Resumable:** the target set is journaled to the state file and the order is
  recomputed from the graph, so a rollback interrupted by a failed delete re-runs
  from disk and converges. This requires delete operations to be idempotent.
- **Best-effort completion:** A failed delete does not prevent subsequent deletes from running. After all possible operations have been attempted, a RollbackError is raised containing the list of failures, with the original apply error preserved as the cause.

## Quickstart

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
orchestrate apply examples/stack.yaml

# Simulate a partial failure roll back: app fails, the durable/protected layers survive.
orchestrate apply examples/stack.yaml --simulate-failure app
```
