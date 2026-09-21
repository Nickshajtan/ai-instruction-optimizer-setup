from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.config.loader import load_config
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.probes.command import TARGET_COMMAND_ENV
from ai_doc.tokens.counter import ApproximateTokenCounter


def _json_check(path: str, *extra: str) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(
        app,
        ["check", path, "--format", "json", "--non-interactive", "--allow-extensions", *extra],
    )
    assert result.exit_code in {0, 2, 3}, result.output
    return result.exit_code, json.loads(result.stdout)


def test_basic_example_runs_static_check() -> None:
    exit_code, report = _json_check("examples/basic")

    assert exit_code == 0
    assert "AGENTS.md" in report["profiles"]
    assert report["profiles"]["AGENTS.md"] == "instruction"
    assert report["files_analyzed"] >= 2


def test_process_extension_example_uses_configured_evaluator() -> None:
    exit_code, report = _json_check("examples/extensions", "--deep")

    assert exit_code == 0
    assert report["evaluation"]["engine"] == "simple-process-evaluator"
    assert report["evaluation"]["passed"] is True


def test_conflicting_instructions_example_reports_expected_findings() -> None:
    _exit_code, report = _json_check("examples/conflicting-instructions")

    codes = {finding["code"] for finding in report["findings"]}
    assert "RISK_LITERAL_CONTRADICTION" in codes
    assert "FINOPS_DUPLICATE_LIST_ITEM" in codes
    assert "CLARITY_AMBIGUOUS_RULE" in codes


def test_hierarchical_config_example_scopes_nested_config() -> None:
    root = Path("examples/hierarchical-config")
    snapshot = discover_markdown(root, load_config(root), ApproximateTokenCounter())

    profiles = {document.relative_path: document.profile for document in snapshot.documents}
    assert profiles["AGENTS.md"] is DocumentProfile.INSTRUCTION
    assert profiles["packages/backend/AGENTS.md"] is DocumentProfile.INSTRUCTION
    assert profiles["packages/backend/docs/api.md"] is DocumentProfile.REFERENCE
    assert "packages/backend/docs/private.md" not in profiles


def test_multi_agent_example_discovers_supported_ecosystems() -> None:
    root = Path("examples/multi-agent")
    snapshot = discover_markdown(root, load_config(root), ApproximateTokenCounter())

    profiles = {document.relative_path: document.profile for document in snapshot.documents}
    assert profiles["AGENTS.md"] is DocumentProfile.INSTRUCTION
    assert profiles["CLAUDE.md"] is DocumentProfile.INSTRUCTION
    assert profiles["GEMINI.md"] is DocumentProfile.INSTRUCTION
    assert profiles[".github/copilot-instructions.md"] is DocumentProfile.INSTRUCTION
    assert profiles[".github/instructions/backend.instructions.md"] is DocumentProfile.INSTRUCTION
    assert profiles[".codex/skills/review/SKILL.md"] is DocumentProfile.SKILL
    assert profiles[".claude/skills/review/SKILL.md"] is DocumentProfile.SKILL
    assert profiles[".gemini/skills/review/SKILL.md"] is DocumentProfile.SKILL
    assert profiles[".agents/skills/shared-review/SKILL.md"] is DocumentProfile.SKILL
    assert profiles[".cursor/rules/backend.mdc"] is DocumentProfile.INSTRUCTION


def test_target_probe_example_runs_plan_and_execute(monkeypatch) -> None:
    command = f'"{sys.executable}" fake_target.py'
    monkeypatch.setenv(TARGET_COMMAND_ENV, command)
    runner = CliRunner()

    probe = runner.invoke(app, ["probe", "examples/target-probe", "--allow-extensions"])
    assert probe.exit_code == 0, probe.output
    probe_report = json.loads(probe.stdout)
    planned = probe_report["observations"][0]["observation"]
    assert planned["target"] == "fake-target"
    assert "write a summary artifact during execution" in planned["planned_actions"]

    execute = runner.invoke(app, ["execute", "examples/target-probe", "--allow-extensions"])
    assert execute.exit_code == 0, execute.output
    execute_report = json.loads(execute.stdout)
    executed = execute_report["observations"][0]["observation"]
    assert executed["status"] == "succeeded"
    assert executed["workspace_delta"]["created_paths"] == ["target-output.txt"]
    assert not Path("examples/target-probe/target-output.txt").exists()
