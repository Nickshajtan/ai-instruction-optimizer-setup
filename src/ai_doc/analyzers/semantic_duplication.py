from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.ml import (
    LocalModelUnavailableError,
    NLIEngine,
    NLIRelation,
    SemanticSimilarityEngine,
    SentenceTransformerSimilarityEngine,
    SentenceTransformersNLIEngine,
)

FINOPS_SEMANTIC_DUPLICATE = "FINOPS_SEMANTIC_DUPLICATE"
FINOPS_STRONG_SEMANTIC_DUPLICATE = "FINOPS_STRONG_SEMANTIC_DUPLICATE"
RISK_LOCAL_ML_UNAVAILABLE = "RISK_LOCAL_ML_UNAVAILABLE"
MIN_SEMANTIC_SPAN_LENGTH = 20


@dataclass(frozen=True)
class SemanticSpan:
    text: str
    path: str
    section: str | None


class SemanticDuplicationAnalyzer:
    def __init__(
        self,
        similarity_engine: SemanticSimilarityEngine | None = None,
        nli_engine: NLIEngine | None = None,
    ) -> None:
        self._similarity_engine = similarity_engine
        self._nli_engine = nli_engine

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        config = context.config.local_ml
        if not config.enabled or not config.semantic_duplication:
            return []
        similarity_engine = self._similarity_engine
        if similarity_engine is None:
            try:
                similarity_engine = SentenceTransformerSimilarityEngine(config.similarity_model)
            except LocalModelUnavailableError as exc:
                return [_unavailable(str(exc))]

        nli_engine = self._nli_engine
        nli_unavailable: str | None = None
        if nli_engine is None:
            try:
                nli_engine = SentenceTransformersNLIEngine(config.nli_model)
            except LocalModelUnavailableError as exc:
                nli_unavailable = str(exc)

        findings: list[Finding] = []
        for left, right in combinations(_spans(context), 2):
            if left.text.casefold() == right.text.casefold():
                continue
            similarity = similarity_engine.similarity(left.text, right.text)
            if similarity < config.similarity_threshold:
                continue

            relation_evidence: dict[str, object] = {}
            strong = False
            if nli_engine is not None:
                forward = nli_engine.classify(left.text, right.text)
                reverse = nli_engine.classify(right.text, left.text)
                relation_evidence = {
                    "left_entails_right": forward.model_dump(mode="json"),
                    "right_entails_left": reverse.model_dump(mode="json"),
                }
                strong = _confident_entailment(forward, config.nli_confidence_threshold) and _confident_entailment(
                    reverse,
                    config.nli_confidence_threshold,
                )
            elif nli_unavailable:
                relation_evidence = {"nli": "unavailable", "detail": nli_unavailable}

            findings.append(
                Finding(
                    code=FINOPS_STRONG_SEMANTIC_DUPLICATE if strong else FINOPS_SEMANTIC_DUPLICATE,
                    category=FindingCategory.FINOPS,
                    severity=FindingSeverity.WARNING,
                    path=left.path,
                    section=left.section,
                    message=(
                        "Semantically equivalent documentation likely duplicates context."
                        if strong
                        else "Semantically similar documentation may duplicate context."
                    ),
                    evidence={
                        "evidence_level": "strong_bidirectional_entailment" if strong else "probable_similarity",
                        "similarity": round(similarity, 4),
                        "similarity_threshold": config.similarity_threshold,
                        "nli_confidence_threshold": config.nli_confidence_threshold,
                        "left": {"path": left.path, "section": left.section, "text": left.text},
                        "right": {"path": right.path, "section": right.section, "text": right.text},
                        **relation_evidence,
                    },
                    suggestion=(
                        "Review whether one equivalent passage can be removed or replaced with a route to the canonical rule."
                        if strong
                        else "Review whether both passages are needed; similarity alone is not proof of equivalence."
                    ),
                )
            )
        return findings


def _confident_entailment(result: object, threshold: float) -> bool:
    relation = getattr(result, "relation", None)
    confidence = float(getattr(result, "confidence", 0.0))
    return relation == NLIRelation.ENTAILMENT and confidence >= threshold


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
