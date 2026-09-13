from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.ml import LocalModelUnavailableError, NLIEngine, NLIRelation, SentenceTransformersNLIEngine

RISK_SEMANTIC_CONTRADICTION = "RISK_SEMANTIC_CONTRADICTION"
RISK_LOCAL_ML_UNAVAILABLE = "RISK_LOCAL_ML_UNAVAILABLE"
MIN_RULE_LENGTH = 3


class RulePolarity(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class SemanticRule:
    polarity: RulePolarity
    proposition: str
    path: str
    section: str | None
    evidence: str


class SemanticContradictionAnalyzer:
    def __init__(self, nli_engine: NLIEngine | None = None) -> None:
        self._nli_engine = nli_engine

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        config = context.config.local_ml
        if not config.enabled or not config.semantic_contradiction:
            return []
        engine = self._nli_engine
        if engine is None:
            try:
                engine = SentenceTransformersNLIEngine(config.nli_model)
            except LocalModelUnavailableError as exc:
                return [_unavailable(str(exc))]
        findings: list[Finding] = []
        for left, right in combinations(_rules(context), 2):
            if left.proposition == right.proposition and left.polarity != right.polarity:
                continue
            forward = engine.classify(left.evidence, right.evidence)
            reverse = engine.classify(right.evidence, left.evidence)
            confidence = max(
                (result.confidence for result in (forward, reverse) if result.relation == NLIRelation.CONTRADICTION),
                default=0.0,
            )
            if confidence < config.nli_confidence_threshold:
                continue
            findings.append(
                Finding(
                    code=RISK_SEMANTIC_CONTRADICTION,
                    category=FindingCategory.RISK,
                    severity=FindingSeverity.WARNING,
                    path=left.path,
                    section=left.section,
                    message="Local NLI predicts that two normative rules contradict each other.",
                    evidence={
                        "confidence": round(confidence, 4),
                        "threshold": config.nli_confidence_threshold,
                        "left": _location(left),
                        "right": _location(right),
                    },
                    suggestion="Review both rules; NLI is probabilistic evidence, not proof of agent behavior.",
                )
            )
        return findings


def _rules(context: AnalysisContext) -> list[SemanticRule]:
    rules: list[SemanticRule] = []
    for document in context.snapshot.documents:
        for section in document.sections:
            section_name = section.heading.title if section.heading else None
            for sentence in _sentences(section.text):
                parsed = _parse_rule(sentence, document.relative_path, section_name)
                if parsed is not None:
                    rules.append(parsed)
    return rules


_FORBIDDEN = re.compile(r"^\s*(?:must\s+not|never|forbidden\s+to)\s+(.+?)\s*[.!?]?\s*$", re.IGNORECASE)
_REQUIRED = re.compile(r"^\s*(?:must|always|required\s+to)\s+(.+?)\s*[.!?]?\s*$", re.IGNORECASE)


def _parse_rule(sentence: str, path: str, section: str | None) -> SemanticRule | None:
    for polarity, pattern in ((RulePolarity.FORBIDDEN, _FORBIDDEN), (RulePolarity.REQUIRED, _REQUIRED)):
        match = pattern.match(sentence)
        if not match:
            continue
        proposition = _normalize(match.group(1))
        if len(proposition) < MIN_RULE_LENGTH:
            return None
        return SemanticRule(polarity, proposition, path, section, sentence.strip())
    return None


def _sentences(text: str) -> list[str]:
    return [
        part.strip(" -*\t\r\n")
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip(" -*\t\r\n")
    ]


def _normalize(text: str) -> str:
    text = re.sub(r"[`*_]", "", text.lower())
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .!?")


def _location(rule: SemanticRule) -> dict[str, str | None]:
    return {"path": rule.path, "section": rule.section, "rule": rule.evidence}


def _unavailable(detail: str) -> Finding:
    return Finding(
        code=RISK_LOCAL_ML_UNAVAILABLE,
        category=FindingCategory.RISK,
        severity=FindingSeverity.INFO,
        path=".",
        message="Optional local NLI contradiction analysis was skipped.",
        evidence={"detail": detail},
        suggestion="Provision the configured local NLI model or disable local_ml.",
    )
