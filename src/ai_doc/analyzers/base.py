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


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.path, f.category, f.code, f.section or ""))
