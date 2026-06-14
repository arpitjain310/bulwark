import json
import logging

from orchestrator.cli import main

SPEC = """
resources:
  - {name: net, type: vpc, protection: durable}
  - {name: db, type: postgres, depends_on: [net], protection: protected}
  - {name: cache, type: redis, depends_on: [net]}
  - {name: app, type: service, depends_on: [db, cache]}
"""


def _write_spec(tmp_path):
    spec = tmp_path / "stack.yaml"
    spec.write_text(SPEC)
    return spec


def _events(caplog):
    return {
        (json.loads(r.getMessage())["resource"], json.loads(r.getMessage())["action"])
        for r in caplog.records
        if r.name == "bulwark"
    }


def test_cli_apply_reports_success(tmp_path, capsys):
    spec = _write_spec(tmp_path)
    rc = main(["apply", str(spec), "--state", str(tmp_path / "s.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied 4 resources" in out


def test_cli_simulate_failure_rolls_back_preserving_durable(tmp_path, capsys, caplog):
    caplog.set_level(logging.INFO, logger="bulwark")
    spec = _write_spec(tmp_path)
    rc = main(
        ["apply", str(spec), "--state", str(tmp_path / "s.json"), "--simulate-failure", "app"]
    )
    assert rc == 1
    assert "apply failed" in capsys.readouterr().out

    events = _events(caplog)
    assert ("cache", "deleted") in events     # ephemeral torn down on rollback
    assert ("db", "preserved") in events      # protected kept
    assert ("net", "preserved") in events     # durable kept


def test_cli_simulate_failure_rejected_for_aws(tmp_path, capsys):
    spec = _write_spec(tmp_path)
    try:
        main(["apply", str(spec), "--provider", "aws", "--simulate-failure", "app"])
    except SystemExit as exc:
        assert exc.code == 2
    assert "only with --provider mock" in capsys.readouterr().out
