from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.probes.workspace import UnsafeWorkspaceError, isolated_workspace

CONTROL_PLANE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".ai/skills/security/SKILL.md",
    ".codex/skills/security/SKILL.md",
    ".claude/skills/security/SKILL.md",
    ".github/workflows/security.yml",
    "docs/standards.md",
)


def test_python_extension_cannot_execute_without_authorization(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    side_effect = tmp_path / "executed.txt"
    (tmp_path / ".ai-doc.yaml").write_text(
        "version: 1\ninclude: []\nextensions:\n  - path: .ai-doc/extensions/malicious.py\n",
        encoding="utf-8",
    )
    (extension_dir / "malicious.py").write_text(
        f"from pathlib import Path\nPath({str(side_effect)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "--allow-extensions" in result.output
    assert not side_effect.exists()


def test_process_extension_cannot_execute_without_authorization(tmp_path: Path) -> None:
    side_effect = tmp_path / "process-executed.txt"
    process = tmp_path / "process.py"
    process.write_text(
        f"from pathlib import Path\nPath({str(side_effect)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (tmp_path / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: []
extension_runtime:
  analyzers:
    malicious:
      command: {json.dumps([sys.executable, str(process)])}
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "process:analyzer:malicious" in result.output
    assert not side_effect.exists()


def test_nested_config_cannot_bypass_extension_authorization(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\ninclude: []\n", encoding="utf-8")
    module = tmp_path / "module"
    module.mkdir()
    side_effect = tmp_path / "nested-executed.txt"
    (module / ".ai-doc.yaml").write_text("version: 1\nextensions:\n  - path: extension.py\n", encoding="utf-8")
    (module / "extension.py").write_text(
        f"from pathlib import Path\nPath({str(side_effect)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "python:module/extension.py" in result.output
    assert not side_effect.exists()


def test_finding_adapter_cannot_hide_authoritative_builtin_failure(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
budgets:
  instruction:
    error_tokens: 1
extensions:
  - path: .ai-doc/extensions/suppress.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "suppress.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter


class SuppressErrors(FindingAdapter):
    def adapt_findings(self, context, findings):
        return [finding for finding in findings if finding.severity != "error"]


def register(registry):
    registry.add_finding_adapter(SuppressErrors())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert payload["finding_audit"]["adapter_events"][0]["action"] == "suppressed"


def test_gepa_requires_explicit_models_even_with_ambient_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
optimization:
  strategy: balanced
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\n<!-- ai-doc:gepa -->\n\nRun validation.\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--gepa"])

    assert result.exit_code == 1
    assert "optimization.gepa.reflection_model" in result.output
    assert "optimization.gepa.mutation_model" in result.output


def test_process_extension_does_not_receive_ambient_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")
    observed = tmp_path / "observed-env.json"
    process = tmp_path / "analyzer.py"
    process.write_text(
        """
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

request = json.loads(sys.stdin.read())
Path(sys.argv[1]).write_text(json.dumps({
    "openai": os.getenv("OPENAI_API_KEY"),
    "configured": os.getenv("AI_DOC_SECURITY_TEST_KEY"),
}), encoding="utf-8")
print(json.dumps({
    "protocol": request["protocol"],
    "request_id": request["request_id"],
    "status": "ok",
    "result": {"payload_version": 1, "findings": []},
}))
""",
        encoding="utf-8",
    )
    (tmp_path / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: []
extension_runtime:
  analyzers:
    env-probe:
      command: {json.dumps([sys.executable, str(process), str(observed)])}
      env:
        AI_DOC_SECURITY_TEST_KEY: configured
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--allow-extensions"])

    assert result.exit_code == 0
    environment = json.loads(observed.read_text(encoding="utf-8"))
    assert environment["openai"] is None
    assert environment["configured"] == "configured"


def test_workspace_isolation_rejects_symlink_boundary(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(UnsafeWorkspaceError), isolated_workspace(tmp_path):
        pass


def test_security_workflow_runs_dedicated_security_suite() -> None:
    workflow = _workflow(".github/workflows/security.yml")
    jobs = workflow["jobs"]
    assert jobs
    assert any("tests/security" in step.get("run", "") for job in jobs.values() for step in job.get("steps", []))


def test_control_plane_markdown_is_not_blanket_ignored_by_primary_workflows() -> None:
    for workflow_path in (
        ".github/workflows/ci.yml",
        ".github/workflows/pylint.yml",
        ".github/workflows/branch-tests.yml",
        ".github/workflows/dependency-compatibility.yml",
    ):
        workflow = _workflow(workflow_path)
        for event_name in ("push", "pull_request"):
            event = workflow.get("on", {}).get(event_name, {})
            ignored = event.get("paths-ignore", []) if isinstance(event, dict) else []
            assert "**/*.md" not in ignored
            for path in CONTROL_PLANE_PATHS:
                assert not _path_is_ignored(path, ignored), f"{workflow_path} ignores {path}"


def _workflow(path: str) -> dict[str, object]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _path_is_ignored(path: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(path, pattern) for pattern in patterns)
