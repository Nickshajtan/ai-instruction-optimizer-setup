from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ai_doc.config.models import AiDocConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.findings import Finding
from ai_doc.markdown.graph import DocumentGraph


class AnalysisContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: AiDocConfig
    snapshot: DocumentationSnapshot
    graph: DocumentGraph


class Analyzer(Protocol):
    def analyze(self, context: AnalysisContext) -> list[Finding]: ...


class AnalyzerProvider(Protocol):
    def analyzers(self) -> Sequence[Analyzer]:
        ...


class BuiltInAnalyzerProvider:
    def analyzers(self) -> Sequence[Analyzer]:
        # Built-in analyzers depend on AnalysisContext from this module, so importing
        # them lazily keeps the dependency direction acyclic without splitting the
        # small analyzer contracts into another module.
        from ai_doc.analyzers.clarity import ClarityAnalyzer  # pylint: disable=import-outside-toplevel
        from ai_doc.analyzers.duplication import DuplicationAnalyzer  # pylint: disable=import-outside-toplevel
        from ai_doc.analyzers.finops import FinOpsAnalyzer  # pylint: disable=import-outside-toplevel
        from ai_doc.analyzers.structure import StructureAnalyzer  # pylint: disable=import-outside-toplevel

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


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.path, f.category, f.code, f.section or ""))
