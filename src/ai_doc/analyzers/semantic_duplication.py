from __future__ import annotations

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding


class SemanticDuplicationAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        return []
