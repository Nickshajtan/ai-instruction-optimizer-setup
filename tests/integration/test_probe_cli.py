from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.probes.command import TARGET_COMMAND_ENV


def _fixture_command() -> str:
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_target_probe.py"
    return f'"{sys.executable}" "{fixture}"'


def test_probe_cli_runs_real_command_once_per_scenario(monkeypatch) -> None:
    monkeypatch.setenv(TARGET_COMMAND_ENV, _fixture_command())
    runner = CliRunner()

    result = runner.invoke(app, ["probe", "examples/basic", "--allow-extensions"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert len(report["observations"]) == 1
    verified = report["observations"][0]
    assert verified["observation"]["target"] == "fake-target"
    assert verified["observation"]["cache_key"]
    assert verified["observation"]["usage"]["input_tokens"] == 10
    assert all(item["outcome"] == "satisfied" for item in verified["expectations"])


def test_probe_cli_fails_cleanly_without_target_command(monkeypatch) -> None:
    monkeypatch.delenv(TARGET_COMMAND_ENV, raising=False)
    runner = CliRunner()

    result = runner.invoke(app, ["probe", "examples/basic", "--allow-extensions"])

    assert result.exit_code == 1
    assert TARGET_COMMAND_ENV in result.output
