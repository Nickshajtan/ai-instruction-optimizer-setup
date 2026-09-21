from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def test_project_extension_can_adapt_core_clarity_finding_through_cli(tmp_path: Path) -> None:
    _write_project(tmp_path, extension=False)

    stock = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert stock.exit_code == 0
    stock_findings = json.loads(stock.stdout)["findings"]
    assert _has_finding(stock_findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Architecture")
    assert _has_finding(stock_findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Deployment")

    _write_project(tmp_path, extension=True)
    adapted = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert adapted.exit_code == 0
    adapted_findings = json.loads(adapted.stdout)["findings"]
    assert not _has_finding(adapted_findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Architecture")
    assert _has_finding(adapted_findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Deployment")
    assert _has_finding(adapted_findings, "CLARITY_AMBIGUOUS_RULE", "Rules")


def test_multiple_finding_adapters_compose_in_configured_order(tmp_path: Path) -> None:
    _write_project(tmp_path, extension=False)
    extension_dir = tmp_path / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    _write_extension(
        extension_dir / "first.py",
        """
from ai_doc.api.v1 import AnalysisContext, Finding, FindingCategory, FindingSeverity


class FirstAdapter:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        return [
            Finding(
                code="ORG_ADDED",
                category=FindingCategory.RISK,
                severity=FindingSeverity.INFO,
                path="AGENTS.md",
                section="Architecture",
                message="Added by first adapter.",
            )
        ]

    def adapt_findings(self, context: AnalysisContext, findings: list[Finding]) -> list[Finding]:
        return [finding for finding in findings if finding.section != "Deployment"]


def register(registry):
    registry.add_analyzer(FirstAdapter())
""",
    )
    _write_extension(
        extension_dir / "second.py",
        """
from ai_doc.api.v1 import AnalysisContext, Finding


class SecondAdapter:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        return []

    def adapt_findings(self, context: AnalysisContext, findings: list[Finding]) -> list[Finding]:
        return [finding for finding in findings if finding.code != "ORG_ADDED"]


def register(registry):
    registry.add_analyzer(SecondAdapter())
""",
    )
    _write_config(
        tmp_path,
        """
extensions:
  - path: .ai-doc/extensions/first.py
  - path: .ai-doc/extensions/second.py
""",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    findings = json.loads(result.stdout)["findings"]
    assert _has_finding(findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Architecture")
    assert not _has_finding(findings, "CLARITY_NO_ACTIONABLE_CONTENT", "Deployment")
    assert not _has_finding(findings, "ORG_ADDED", "Architecture")
    assert _has_finding(findings, "CLARITY_AMBIGUOUS_RULE", "Rules")


def _write_project(root: Path, *, extension: bool) -> None:
    extension_block = "\nextensions:\n  - path: .ai-doc/extensions/adapt_clarity.py\n" if extension else ""
    _write_config(root, extension_block)
    (root / "AGENTS.md").write_text(
        "# Rules\n\n"
        "Use best practices.\n\n"
        "## Architecture\n\n"
        "The platform has service boundaries, historical deployment constraints, ownership maps, "
        "integration notes, and operational background for maintainers who need context before "
        "changing instructions. It also records subsystem terminology, dependency history, "
        "migration notes, service catalog labels, release governance, support expectations, "
        "and review context for future documentation work.\n\n"
        "## Deployment\n\n"
        "Production deployment is coordinated through release windows, environment ownership, "
        "approval records, change calendars, and platform status pages for stakeholders. The "
        "section captures scheduling background, ownership context, historical constraints, "
        "communication channels, release coordination details, escalation notes, audit history, "
        "maintenance calendars, stakeholder maps, and environment background for maintainers.\n",
        encoding="utf-8",
    )
    if extension:
        extension_dir = root / ".ai-doc" / "extensions"
        extension_dir.mkdir(parents=True, exist_ok=True)
        (extension_dir / "adapt_clarity.py").write_text(
            """
from ai_doc.api.v1 import AnalysisContext, Finding


class ProjectClarityAdapter:
    reference_sections = {"Architecture"}

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        return []

    def adapt_findings(self, context: AnalysisContext, findings: list[Finding]) -> list[Finding]:
        return [
            finding
            for finding in findings
            if not (
                finding.code == "CLARITY_NO_ACTIONABLE_CONTENT"
                and finding.section in self.reference_sections
            )
        ]


def register(registry):
    registry.add_analyzer(ProjectClarityAdapter())
""",
            encoding="utf-8",
        )


def _write_config(root: Path, extra: str = "") -> None:
    (root / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
{extra}
""",
        encoding="utf-8",
    )


def _write_extension(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _has_finding(findings: list[dict[str, object]], code: str, section: str) -> bool:
    return any(finding["code"] == code and finding.get("section") == section for finding in findings)
