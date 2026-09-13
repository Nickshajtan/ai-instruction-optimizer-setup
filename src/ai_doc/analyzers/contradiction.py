from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity

RISK_LITERAL_CONTRADICTION = "RISK_LITERAL_CONTRADICTION"
MIN_RULE_LENGTH = 3


class RulePolarity(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class LiteralRule:
    polarity: RulePolarity
    proposition: str
    path: str
    section: str | None
    evidence: str


class ContradictionAnalyzer:
    """Detect only contradictions that are provable from literal normative wording.

    This analyzer intentionally prefers false negatives over semantic guesses. Two
    rules conflict only when their normalized proposition is identical and one
    requires it while the other forbids it.
    """

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        by_proposition: dict[str, list[LiteralRule]] = defaultdict(list)
        for document in context.snapshot.documents:
            for section in document.sections:
                section_name = section.heading.title if section.heading else None
                for sentence in _sentences(section.text):
                    rule = _parse_literal_rule(sentence, document.relative_path, section_name)
                    if rule is not None:
                        by_proposition[rule.proposition].append(rule)

        findings: list[Finding] = []
        for proposition, rules in by_proposition.items():
            required = [rule for rule in rules if rule.polarity == RulePolarity.REQUIRED]
            forbidden = [rule for rule in rules if rule.polarity == RulePolarity.FORBIDDEN]
            if not required or not forbidden:
                continue
            first = required[0]
            findings.append(
                Finding(
                    code=RISK_LITERAL_CONTRADICTION,
                    category=FindingCategory.RISK,
                    severity=FindingSeverity.ERROR,
                    path=first.path,
                    section=first.section,
                    message="Literal normative rules require and forbid the same proposition.",
                    evidence={
                        "proposition": proposition,
                        "required": [_location(rule) for rule in required],
                        "forbidden": [_location(rule) for rule in forbidden],
                    },
                    suggestion="Remove or scope one of the conflicting rules so only one literal requirement applies.",
                )
            )
        return findings


_FORBIDDEN_PATTERNS = (
    re.compile(r"^\s*(?:must\s+not|never|forbidden\s+to)\s+(.+?)\s*[.!?]?\s*$", re.IGNORECASE),
)
_REQUIRED_PATTERNS = (
    re.compile(r"^\s*(?:must|always|required\s+to)\s+(.+?)\s*[.!?]?\s*$", re.IGNORECASE),
)


def _parse_literal_rule(sentence: str, path: str, section: str | None) -> LiteralRule | None:
    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.match(sentence)
        if match:
            return _rule(RulePolarity.FORBIDDEN, match.group(1), path, section, sentence)
    for pattern in _REQUIRED_PATTERNS:
        match = pattern.match(sentence)
        if match:
            return _rule(RulePolarity.REQUIRED, match.group(1), path, section, sentence)
    return None


def _rule(
    polarity: RulePolarity,
    proposition: str,
    path: str,
    section: str | None,
    evidence: str,
) -> LiteralRule | None:
    normalized = _normalize_proposition(proposition)
    if len(normalized) < MIN_RULE_LENGTH:
        return None
    return LiteralRule(
        polarity=polarity,
        proposition=normalized,
        path=path,
        section=section,
        evidence=evidence.strip(),
    )


def _sentences(text: str) -> list[str]:
    return [
        part.strip(" -*\t\r\n")
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if part.strip(" -*\t\r\n")
    ]


def _normalize_proposition(text: str) -> str:
    text = re.sub(r"[`*_]", "", text.lower())
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .!?")


def _location(rule: LiteralRule) -> dict[str, str | None]:
    return {
        "path": rule.path,
        "section": rule.section,
        "rule": rule.evidence,
    }
