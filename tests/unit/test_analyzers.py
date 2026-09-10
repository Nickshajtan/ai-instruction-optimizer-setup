from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext, run_analyzers
from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_static_findings_include_clarity_and_duplication(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST validate changes.\n"
        "- Use best practices.\n"
        "- Repeat this operational rule.\n"
        "- Repeat this operational rule.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)
    codes = {finding.code for finding in report.findings}
    assert "CLARITY_AMBIGUOUS_RULE" in codes
    assert "FINOPS_DUPLICATE_LIST_ITEM" in codes


class CustomAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        document = context.snapshot.documents[0]
        return [
            Finding(
                code="CUSTOM_SORTED",
                category=FindingCategory.RISK,
                severity=FindingSeverity.INFO,
                path=document.relative_path,
                message="Custom analyzer ran.",
            )
        ]


def test_run_analyzers_accepts_custom_analyzer_sequence(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nCustom content.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    context = AnalysisContext(config=DEFAULT_CONFIG, snapshot=snapshot, graph=DocumentGraph(snapshot))

    findings = run_analyzers(context, analyzers=[CustomAnalyzer()])

    assert [finding.code for finding in findings] == ["CUSTOM_SORTED"]
