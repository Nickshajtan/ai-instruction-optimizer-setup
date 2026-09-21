from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from ai_doc.app import _adapter_audit_events, _finding_snapshot
from ai_doc.cli.main import app
from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.domain.probes import ExecutionObservation, ExecutionStatus
from ai_doc.extension_trust import ExtensionTrustError, ensure_extensions_authorized
from ai_doc.probes.command import TARGET_COMMAND_ENV
from ai_doc.probes.execution_runner import ExecutionActionVerifier, ExecutionProbeRunner
from ai_doc.probes.workspace import UnsafeWorkspaceError, isolated_workspace

CONTROL_PLANE_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".ai/skills/security-review/SKILL.md",
    ".ai/skills/safe-external-execution/SKILL.md",
    ".github/workflows/security.yml",
    "docs/standards.md",
)

SECURITY_MUTATION_TARGETS = (
    "src/ai_doc/app.py",
    "src/ai_doc/extension_trust.py",
    "src/ai_doc/extensions/transport.py",
    "src/ai_doc/optimizer/prompt_suboptimizer.py",
    "src/ai_doc/probes/execution_runner.py",
    "src/ai_doc/probes/workspace.py",
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


def test_extension_trust_error_preserves_structured_declarations(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        "version: 1\ninclude: []\nextensions:\n  - path: .ai-doc/extensions/review.py\n",
        encoding="utf-8",
    )
    from ai_doc.config.loader import load_config

    config = load_config(tmp_path)

    with pytest.raises(ExtensionTrustError) as exc_info:
        ensure_extensions_authorized(config, allow_extensions=False)

    assert exc_info.value.declarations == ("python:.ai-doc/extensions/review.py",)
    assert "python:.ai-doc/extensions/review.py" in str(exc_info.value)


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
    assert payload["finding_audit"]["adapter_events"][0]["adapter"].endswith(".SuppressErrors")


def test_finding_adapter_mutating_builtin_error_in_place_remains_blocking(tmp_path: Path) -> None:
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
  - path: .ai-doc/extensions/mutate.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "mutate.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter, FindingSeverity


class MutateErrors(FindingAdapter):
    def adapt_findings(self, context, findings):
        for finding in findings:
            if finding.severity == FindingSeverity.ERROR:
                finding.severity = FindingSeverity.INFO
        return findings


def register(registry):
    registry.add_finding_adapter(MutateErrors())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert [finding["severity"] for finding in payload["findings"]] == ["info"]
    assert payload["finding_audit"]["adapter_events"] == [
        {
            "adapter": payload["finding_audit"]["adapter_events"][0]["adapter"],
            "code": "FINOPS_BUDGET_ERROR",
            "severity": "error",
            "path": "AGENTS.md",
            "section": None,
            "action": "severity_changed",
        }
    ]
    assert payload["finding_audit"]["adapter_events"][0]["adapter"].endswith(".MutateErrors")


def test_finding_adapter_audit_attributes_only_current_transition(tmp_path: Path) -> None:
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
  - path: .ai-doc/extensions/chain.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "chain.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter, FindingSeverity


class DowngradeErrors(FindingAdapter):
    def adapt_findings(self, context, findings):
        for finding in findings:
            if finding.severity == FindingSeverity.ERROR:
                finding.severity = FindingSeverity.WARNING
        return findings


class LeaveUnchanged(FindingAdapter):
    def adapt_findings(self, context, findings):
        return findings


def register(registry):
    registry.add_finding_adapter(DowngradeErrors())
    registry.add_finding_adapter(LeaveUnchanged())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert [finding["severity"] for finding in payload["findings"]] == ["warning"]
    assert payload["finding_audit"]["adapter_events"] == [
        {
            "adapter": payload["finding_audit"]["adapter_events"][0]["adapter"],
            "code": "FINOPS_BUDGET_ERROR",
            "severity": "error",
            "path": "AGENTS.md",
            "section": None,
            "action": "severity_changed",
        }
    ]
    assert payload["finding_audit"]["adapter_events"][0]["adapter"].endswith(".DowngradeErrors")


def test_finding_adapter_metadata_mutation_is_audited(tmp_path: Path) -> None:
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
  - path: .ai-doc/extensions/metadata.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "metadata.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter, FindingSeverity


class RewriteMetadata(FindingAdapter):
    def adapt_findings(self, context, findings):
        for finding in findings:
            if finding.severity == FindingSeverity.ERROR:
                finding.message = "Rewritten by adapter."
                finding.section = "Rewritten"
        return findings


def register(registry):
    registry.add_finding_adapter(RewriteMetadata())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert payload["finding_audit"]["adapter_events"][0]["action"] == "metadata_changed"
    assert payload["finding_audit"]["adapter_events"][0]["adapter"].endswith(".RewriteMetadata")


def test_finding_adapter_equivalent_replacement_is_not_false_suppression(tmp_path: Path) -> None:
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
  - path: .ai-doc/extensions/replace.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "replace.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter, FindingSeverity


class ReplaceEquivalent(FindingAdapter):
    def adapt_findings(self, context, findings):
        return [
            finding.model_copy()
            if finding.severity == FindingSeverity.ERROR
            else finding
            for finding in findings
        ]


def register(registry):
    registry.add_finding_adapter(ReplaceEquivalent())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert payload["finding_audit"]["adapter_events"] == []


def test_finding_adapter_equivalent_replacement_with_severity_change_is_audited(tmp_path: Path) -> None:
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
  - path: .ai-doc/extensions/replace_downgrade.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation before merge.\n", encoding="utf-8")
    (extension_dir / "replace_downgrade.py").write_text(
        """
from ai_doc.api.v1 import FindingAdapter, FindingSeverity


class ReplaceAndDowngrade(FindingAdapter):
    def adapt_findings(self, context, findings):
        return [
            finding.model_copy(update={"severity": FindingSeverity.WARNING})
            if finding.severity == FindingSeverity.ERROR
            else finding
            for finding in findings
        ]


def register(registry):
    registry.add_finding_adapter(ReplaceAndDowngrade())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["finding_audit"]["builtin_error_count"] == 1
    assert payload["finding_audit"]["adapter_events"][0]["action"] == "severity_changed"
    assert payload["finding_audit"]["adapter_events"][0]["adapter"].endswith(".ReplaceAndDowngrade")


def test_finding_adapter_audit_matches_duplicate_logical_findings_as_multiset() -> None:
    first = _audit_test_finding()
    second = _audit_test_finding()
    before = [_finding_snapshot(first), _finding_snapshot(second)]
    builtin = list(before)
    after = [_finding_snapshot(first.model_copy(update={"severity": FindingSeverity.WARNING})), _finding_snapshot(second)]

    events = _adapter_audit_events("tests.DuplicateAdapter", builtin, before, after)

    assert [event.action for event in events] == ["severity_changed"]


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
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_ACCESS_KEY_ID", "GITHUB_TOKEN", "HOME", "USERPROFILE"):
        monkeypatch.setenv(key, f"ambient-{key.lower()}")
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
    "ambient": {
        key: os.getenv(key)
        for key in [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "GITHUB_TOKEN",
            "HOME",
            "USERPROFILE",
        ]
    },
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
    assert environment["ambient"] == {
        "OPENAI_API_KEY": None,
        "ANTHROPIC_API_KEY": None,
        "AWS_ACCESS_KEY_ID": None,
        "GITHUB_TOKEN": None,
        "HOME": None,
        "USERPROFILE": None,
    }
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


def test_probe_integrity_marks_unreported_workspace_mutation_uncertain(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    suite = EvaluationSuite(scenarios=[_scenario()])

    report = ExecutionProbeRunner(_SilentMutationProbe(), ExecutionActionVerifier()).run(snapshot, suite)

    observation = report.observations[0].observation
    assert observation.workspace_delta.created_paths == ["unreported.txt"]
    assert observation.status == ExecutionStatus.UNCERTAIN
    assert "reported no performed actions" in observation.uncertainties[0]


def test_execute_requires_operator_configured_target_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(TARGET_COMMAND_ENV, raising=False)
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\ninclude: [AGENTS.md]\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun the malicious task.\n", encoding="utf-8")
    evals = tmp_path / ".ai-doc" / "evals"
    evals.mkdir(parents=True)
    side_effect = tmp_path / "target-ran.txt"
    evals.joinpath("malicious.yaml").write_text(
        f"""
id: malicious
task: Write {side_effect}.
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["execute", str(tmp_path), "--allow-extensions"])

    assert result.exit_code == 1
    assert TARGET_COMMAND_ENV in result.output
    assert not side_effect.exists()


def test_security_skills_exist_and_are_routed() -> None:
    security_review = Path(".ai/skills/security-review/SKILL.md").read_text(encoding="utf-8")
    safe_execution = Path(".ai/skills/safe-external-execution/SKILL.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    docs_agents = Path("docs/AGENTS.md").read_text(encoding="utf-8")

    assert "Trust boundary:" in security_review
    assert "Can configuration authorize itself?" in security_review
    assert "Safe argument passing is not the same problem as safe authorization." in safe_execution
    assert ".ai/skills/security-review/SKILL.md" in agents
    assert ".ai/skills/safe-external-execution/SKILL.md" in agents
    assert "../.ai/skills/security-review/SKILL.md" in docs_agents
    assert "../.ai/skills/safe-external-execution/SKILL.md" in docs_agents


def test_agent_specific_skills_mirror_shared_skill_wrappers() -> None:
    shared = _skill_names(".ai/skills")
    for agent_dir in (".codex/skills", ".claude/skills"):
        agent = _skill_names(agent_dir)
        assert agent == shared
        for name in shared:
            content = Path(agent_dir, name, "SKILL.md").read_text(encoding="utf-8-sig")
            assert f".ai/skills/{name}/SKILL.md" in content
            assert "adapter" in content
            assert "routing only" in content


def test_security_workflow_runs_dedicated_security_suite() -> None:
    workflow = _workflow(".github/workflows/security.yml")
    jobs = workflow["jobs"]
    assert jobs
    assert any("tests/security" in step.get("run", "") for job in jobs.values() for step in job.get("steps", []))
    assert workflow.get("permissions") == {"contents": "read"}
    assert "pull_request_target" not in _workflow_events(workflow)


def test_security_workflow_runs_blocking_scanners_without_duplicate_mutation() -> None:
    workflow = _workflow(".github/workflows/security.yml")
    jobs = workflow["jobs"]

    assert _job_has_run(jobs["static"], "python -m bandit -r src --severity-level medium --confidence-level medium")
    assert _job_has_run(jobs["dependencies"], "python -m pip_audit --local --cache-dir .pip-audit-cache")
    assert not _job_uses_continue_on_error(jobs["contracts"])
    assert not _job_uses_continue_on_error(jobs["static"])
    assert not _job_uses_continue_on_error(jobs["dependencies"])
    assert "mutation" not in jobs


def test_security_mutation_scope_includes_security_decision_logic() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    mutmut = pyproject["tool"]["mutmut"]

    assert "tests/security" in mutmut["pytest_add_cli_args_test_selection"]
    for target in SECURITY_MUTATION_TARGETS:
        assert target in mutmut["only_mutate"]


def test_control_plane_markdown_is_not_blanket_ignored_by_primary_workflows() -> None:
    for workflow_path in (
        ".github/workflows/ci.yml",
        ".github/workflows/pylint.yml",
        ".github/workflows/branch-tests.yml",
        ".github/workflows/dependency-compatibility.yml",
    ):
        workflow = _workflow(workflow_path)
        for event_name in ("push", "pull_request"):
            event = _workflow_events(workflow).get(event_name, {})
            ignored = event.get("paths-ignore", []) if isinstance(event, dict) else []
            assert "**/*.md" not in ignored
            for path in CONTROL_PLANE_PATHS:
                assert not _path_is_ignored(path, ignored), f"{workflow_path} ignores {path}"


def test_mutation_workflow_control_plane_scope_is_explicit() -> None:
    workflow = _workflow(".github/workflows/mutation-testing.yml")
    pull_request = _workflow_events(workflow).get("pull_request", {})
    paths = pull_request.get("paths", [])

    assert "!**/*.md" not in paths
    for path in (
        "AGENTS.md",
        "CLAUDE.md",
        ".ai/**",
        ".codex/**",
        ".claude/**",
        ".github/workflows/mutation-testing.yml",
        "docs/standards.md",
        "docs/design/**",
        "docs/operations/testing-and-release.md",
    ):
        assert path in paths


def test_mutation_workflow_precondition_matches_authoritative_test_selection() -> None:
    workflow = _workflow(".github/workflows/mutation-testing.yml")
    jobs = workflow["jobs"]

    assert _job_has_run(jobs["baseline"], "python -m pytest tests/unit tests/integration tests/security")


def test_dependency_compatibility_uses_packaging_requirement_parser() -> None:
    workflow_text = Path(".github/workflows/dependency-compatibility.yml").read_text(encoding="utf-8")

    assert "python -m tools.minimum_constraints pyproject.toml minimum-constraints.txt" in workflow_text
    assert "import re" not in workflow_text
    assert "bandit[toml]" not in workflow_text


def test_primary_markdown_ci_breadth_is_documented_as_conservative() -> None:
    testing_docs = Path("docs/operations/testing-and-release.md").read_text(encoding="utf-8")

    assert "primary workflows intentionally keep broad Markdown triggering" in testing_docs
    assert "control-plane Markdown" in testing_docs


def test_probe_execute_trust_boundary_docs_do_not_claim_host_sandboxing() -> None:
    execution_docs = Path("docs/design/execution-probes.md").read_text(encoding="utf-8")
    behavioral_docs = Path("docs/design/behavioral-evaluation.md").read_text(encoding="utf-8")

    assert "workspace isolation" in execution_docs
    assert "not an OS security sandbox" in execution_docs
    assert "normal OS authority" in behavioral_docs
    assert TARGET_COMMAND_ENV in behavioral_docs


def _workflow(path: str) -> dict[str, object]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _workflow_events(workflow: dict[str, object]) -> dict[str, object]:
    events = workflow.get("on", workflow.get(True, {}))
    return events if isinstance(events, dict) else {}


def _path_is_ignored(path: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(path, pattern) for pattern in patterns)


def _skill_names(root: str) -> set[str]:
    return {path.parent.name for path in Path(root).glob("*/SKILL.md")}


def _job_has_run(job: Any, command: str) -> bool:
    return any(command in step.get("run", "") for step in job.get("steps", []))


def _job_uses_continue_on_error(job: Any) -> bool:
    if job.get("continue-on-error") is True:
        return True
    return any(step.get("continue-on-error") is True for step in job.get("steps", []))


def _snapshot(tmp_path: Path) -> DocumentationSnapshot:
    text = "# Rules\nRun validation.\n"
    path = tmp_path / "AGENTS.md"
    path.write_text(text, encoding="utf-8")
    document = Document(
        path=path,
        relative_path="AGENTS.md",
        profile=DocumentProfile.INSTRUCTION,
        text=text,
        token_count=4,
    )
    return DocumentationSnapshot(root=tmp_path, documents=(document,))


def _scenario() -> EvaluationScenario:
    return EvaluationScenario(id="change", task="Change docs")


def _audit_test_finding() -> Finding:
    return Finding(
        code="DUPLICATE",
        category=FindingCategory.RISK,
        severity=FindingSeverity.ERROR,
        path="AGENTS.md",
        section="Rules",
        message="Same logical finding.",
    )


class _SilentMutationProbe:
    def run(
        self,
        workspace_root: Path,
        _snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        (workspace_root / "unreported.txt").write_text("changed", encoding="utf-8")
        return ExecutionObservation(
            target="codex",
            scenario_id=scenario.id,
            status=ExecutionStatus.SUCCEEDED,
            performed_actions=[],
        )
