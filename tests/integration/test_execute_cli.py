from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.probes.command import TARGET_COMMAND_ENV


def _fixture_command() -> str:
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_target_execute.py"
    return f'"{sys.executable}" "{fixture}"'


def test_execute_cli_runs_target_in_temporary_workspace(monkeypatch) -> None:
    monkeypatch.setenv(TARGET_COMMAND_ENV, _fixture_command())
    runner = CliRunner()

    result = runner.invoke(app, ["execute", "examples/basic", "--allow-extensions"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    verified = report["observations"][0]
    observation = verified["observation"]
    assert observation["target"] == "fake-target"
    assert observation["status"] == "succeeded"
    assert observation["workspace_delta"]["created_paths"] == ["execution-probe.txt"]
    assert observation["usage"]["input_tokens"] == 20
    assert all(item["outcome"] == "satisfied" for item in verified["expectations"])
    assert not Path("examples/basic/execution-probe.txt").exists()
