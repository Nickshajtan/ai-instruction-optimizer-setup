from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.config.models import EvaluationEngine
from ai_doc.domain.evaluations import EvaluationResult
from ai_doc.optional_dependencies import DependencyStatus


def test_project_extension_adds_finding_and_nested_check_discovers_root(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
extensions:
  - path: .ai-doc/extensions/custom_rules.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nCustom extension trigger.\n", encoding="utf-8")
    (extension_dir / "custom_rules.py").write_text(
        """
from ai_doc.api.v1 import Finding


class CustomAnalyzer:
    def analyze(self, context):
        return [
            Finding(
                code="CUSTOM_TRIGGER",
                category="risk",
                severity="info",
                path="AGENTS.md",
                section=None,
                message="custom extension ran",
                evidence={},
                suggestion=None,
            )
        ]


def register(registry):
    registry.add_analyzer(CustomAnalyzer())
""",
        encoding="utf-8",
    )
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(app, ["check", str(nested), "--format", "json", "--allow-extensions"])
    assert result.exit_code == 0
    assert "CUSTOM_TRIGGER" in result.output


def test_extension_can_use_public_finding_enums(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
extensions:
  - path: .ai-doc/extensions/custom_rules.py
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nCustom extension trigger.\n", encoding="utf-8")
    (extension_dir / "custom_rules.py").write_text(
        """
from ai_doc.api.v1 import Finding, FindingCategory, FindingSeverity


class CustomAnalyzer:
    def analyze(self, context):
        return [
            Finding(
                code="CUSTOM_ENUM_TRIGGER",
                category=FindingCategory.RISK,
                severity=FindingSeverity.INFO,
                path="AGENTS.md",
                section=None,
                message="custom enum extension ran",
                evidence={},
                suggestion=None,
            )
        ]


def register(registry):
    registry.add_analyzer(CustomAnalyzer())
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json", "--allow-extensions"])

    assert result.exit_code == 0
    assert "CUSTOM_ENUM_TRIGGER" in result.output


def test_broken_extension_has_actionable_error(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (tmp_path / ".ai-doc.yaml").write_text(
        "version: 1\ninclude: []\nextensions:\n  - path: .ai-doc/extensions/broken.py\n",
        encoding="utf-8",
    )
    (extension_dir / "broken.py").write_text(
        "def register(registry):\n    registry.add_analyzer(object())\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["check", str(tmp_path), "--allow-extensions"])
    assert result.exit_code == 1
    assert "Failed to load extension" in result.output


def test_configured_python_extension_requires_explicit_cli_authorization(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (tmp_path / ".ai-doc.yaml").write_text(
        "version: 1\ninclude: []\nextensions:\n  - path: .ai-doc/extensions/malicious.py\n",
        encoding="utf-8",
    )
    side_effect = tmp_path / "executed.txt"
    (extension_dir / "malicious.py").write_text(
        f"""
from pathlib import Path

Path({str(side_effect)!r}).write_text("executed", encoding="utf-8")


def register(registry):
    pass
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "Executable extensions are configured but were not executed" in result.output
    assert "--allow-extensions" in result.output
    assert not side_effect.exists()


def test_process_extension_requires_explicit_cli_authorization(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: []
extension_runtime:
  analyzers:
    malicious:
      command: [python, process.py]
""",
        encoding="utf-8",
    )
    (tmp_path / "process.py").write_text("raise SystemExit(99)\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "process:analyzer:malicious" in result.output
    assert "--allow-extensions" in result.output


def test_nested_extension_requires_explicit_cli_authorization(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\ninclude: []\n", encoding="utf-8")
    nested = tmp_path / "module"
    nested.mkdir()
    (nested / ".ai-doc.yaml").write_text(
        "version: 1\nextensions:\n  - path: extension.py\n",
        encoding="utf-8",
    )
    (nested / "extension.py").write_text("raise RuntimeError('should not execute')\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path)])

    assert result.exit_code == 1
    assert "python:module/extension.py" in result.output
    assert "should not execute" not in result.output


def test_doctor_json_and_version_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    doctor = runner.invoke(app, ["doctor", str(tmp_path), "--format", "json"])
    assert doctor.exit_code == 0
    assert '"optional_integrations"' in doctor.output
    version = runner.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.output.strip()


def test_deep_check_can_install_missing_promptfoo_dependency(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
evaluation:
  deep:
    engine: promptfoo
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")
    installed: list[EvaluationEngine] = []

    class FakeEvaluator:
        def evaluate(self, baseline, candidate, suite):
            return EvaluationResult(engine="promptfoo", passed=True)

    monkeypatch.setattr(
        "ai_doc.cli.check.missing_dependencies_for_engine",
        lambda engine: [
            DependencyStatus(
                name="Promptfoo",
                available=False,
                detail="missing CLI",
                install_hint="install promptfoo",
            )
        ],
    )
    monkeypatch.setattr(
        "ai_doc.cli.check.install_missing_for_engine",
        lambda engine: installed.append(engine) or ["promptfoo"],
    )
    monkeypatch.setattr("ai_doc.cli.check._deep_evaluator", lambda engine, debug, model: FakeEvaluator())

    result = CliRunner().invoke(
        app,
        ["check", str(tmp_path), "--deep", "--install-missing", "--format", "json"],
    )

    assert result.exit_code == 0
    assert installed == [EvaluationEngine.PROMPTFOO]
    assert '"evaluation"' in result.output


def test_deep_check_uses_configured_deepeval_engine(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
evaluation:
  deep:
    engine: deepeval
    model: test-model
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")
    engines: list[EvaluationEngine] = []

    class FakeEvaluator:
        def evaluate(self, baseline, candidate, suite):
            return EvaluationResult(engine="deepeval", passed=True)

    monkeypatch.setattr("ai_doc.cli.check.missing_dependencies_for_engine", lambda engine: [])
    monkeypatch.setattr(
        "ai_doc.cli.check._deep_evaluator",
        lambda engine, debug, model: engines.append(engine) or FakeEvaluator(),
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--deep", "--format", "json"])

    assert result.exit_code == 0
    assert engines == [EvaluationEngine.DEEPEVAL]
    assert '"engine": "deepeval"' in result.output


def test_deep_check_deepeval_requires_explicit_model(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
evaluation:
  deep:
    engine: deepeval
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")

    monkeypatch.setattr("ai_doc.cli.check.missing_dependencies_for_engine", lambda engine: [])

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--deep", "--format", "json"])

    assert result.exit_code == 3
    assert "No implicit OpenAI model" in result.output
    assert "Traceback" not in result.output


def test_setup_deep_installs_optional_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_doc.cli.setup.install_deep_dependencies",
        lambda: ["promptfoo", "deepeval>=1.0"],
    )

    result = CliRunner().invoke(app, ["setup", "--deep"])

    assert result.exit_code == 0
    assert "promptfoo" in result.output
    assert "deepeval>=1.0" in result.output
