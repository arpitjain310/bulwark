from orchestrator.cli import main

SPEC = """
resources:
  - {name: net, type: vpc, durable: true}
  - {name: db, type: postgres, depends_on: [net], protected: true}
  - {name: cache, type: redis, depends_on: [net]}
  - {name: app, type: service, depends_on: [db, cache]}
"""


def _write_spec(tmp_path):
    spec = tmp_path / "stack.yaml"
    spec.write_text(SPEC)
    return spec


def test_cli_apply_reports_success(tmp_path, capsys):
    spec = _write_spec(tmp_path)
    rc = main(["apply", str(spec), "--state", str(tmp_path / "s.json")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "applied 4 resources" in out


def test_cli_simulate_failure_rolls_back_preserving_durable(tmp_path, capsys):
    spec = _write_spec(tmp_path)
    rc = main(
        ["apply", str(spec), "--state", str(tmp_path / "s.json"), "--simulate-failure", "app"]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "apply failed" in out
    assert "cache" in out          # ephemeral torn down
    assert "db" in out and "net" in out  # durable + protected preserved
