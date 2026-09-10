from __future__ import annotations

from collections.abc import Sequence

from ai_doc.analyzers.base import AnalysisContext, Analyzer, AnalyzerProvider, sort_findings
from ai_doc.analyzers.clarity import ClarityAnalyzer
from ai_doc.analyzers.duplication import DuplicationAnalyzer
from ai_doc.analyzers.finops import FinOpsAnalyzer
from ai_doc.analyzers.structure import StructureAnalyzer
from ai_doc.domain.findings import Finding


class BuiltInAnalyzerProvider:
    def analyzers(self) -> Sequence[Analyzer]:
        return (
            StructureAnalyzer(),
            FinOpsAnalyzer(),
            DuplicationAnalyzer(),
            ClarityAnalyzer(),
        )


class AnalyzerSuite:
    def __init__(self, analyzers: Sequence[Analyzer]) -> None:
        self._analyzers = tuple(analyzers)

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for analyzer in self._analyzers:
            findings.extend(analyzer.analyze(context))
        return sort_findings(findings)


def run_analyzers(
    context: AnalysisContext, analyzers: Sequence[Analyzer] | None = None
) -> list[Finding]:
    selected = analyzers or BuiltInAnalyzerProvider().analyzers()
    return AnalyzerSuite(selected).analyze(context)


__all__ = ["AnalyzerProvider", "AnalyzerSuite", "BuiltInAnalyzerProvider", "run_analyzers"]
