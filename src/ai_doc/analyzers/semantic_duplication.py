from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.ml import LocalModelUnavailableError, SemanticSimilarityEngine, SentenceTransformerSimilarityEngine

FINOPS_SEMANTIC_DUPLICATE = "FINOPS_SEMANTIC_DUPLICATE"
RISK_LOCAL_ML_UNAVAILABLE = "RISK_LOCAL_ML_UNAVAILABLE"
MIN_SEMANTIC_SPAN_LENGTH = 20


@dataclass(frozen=True)
class SemanticSpan:
    text: str
    path: str
    section: str | None


class SemanticDuplicationAnalyzer:
    def __init__(self, similarity_engine: SemanticSimilarityEngine | None = None) -> None:
        self._similarity_engine = similarity_engine

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        config = context.config.local_ml
        if not config.enabled or not config.semantic_duplication:
            return []
        engine = self._similarity_engine
        if engine is None:
            try:
                engine = SentenceTransformerSimilarityEngine(config.similarity_model)
            except LocalModelUnavailableError as exc:
                return [_unavailable(str(exc))]
        findings: list[Finding] = []
        for left, right in combinations(_spans(context), 2):
            if left.text.casefold() == right.text.casefold():
                continue
            similarity = engine.similarity(left.text, right.text)
            if similarity < config.similarity_threshold:
                continue
            findings.append(
                Finding(
                    code=FINOPS_SEMANTIC_DUPLICATE,
                    category=FindingCategory.FINOPS,
                    severity=FindingSeverity.WARNING,
                    path=left.path,
                    section=left.section,
                    message="Semantically similar documentation may duplicate context.",
                    evidence={
                        "similarity": round(similarity, 4),
                        "threshold": config.similarity_threshold,
                        "left": {"path": left.path, "section": left.section, "text": left.text},
                        "right": {"path": right.path, "section": right.section, "text": right.text},
                    },
                    suggestion="Review whether both passages are needed; similarity is not proof of equivalence.",
                )
            )
        return findings


def _spans(context: AnalysisContext) -> list[SemanticSpan]:
    spans: list[SemanticSpan] = []
    for document in context.snapshot.documents:
        for section in document.sections:
            section_name = section.heading.title if section.heading else None
            for line in section.text.splitlines():
                text = line.strip().removeprefix("-").removeprefix("*").strip()
                if len(text) >= MIN_SEMANTIC_SPAN_LENGTH and not text.startswith("#"):
                    spans.append(SemanticSpan(text, document.relative_path, section_name))
    return spans


def _unavailable(detail: str) -> Finding:
    return Finding(
        code=RISK_LOCAL_ML_UNAVAILABLE,
        category=FindingCategory.RISK,
        severity=FindingSeverity.INFO,
        path=".",
        message="Optional local semantic duplication analysis was skipped.",
        evidence={"detail": detail},
        suggestion="Provision the configured local similarity model or disable local_ml.",
    )
