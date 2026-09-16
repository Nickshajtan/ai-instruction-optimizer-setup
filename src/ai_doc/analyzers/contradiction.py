from __future__ import annotations

from collections import defaultdict

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.analysis import InstructionUnit, Polarity
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.markdown.extraction import DeterministicInstructionExtractor

RISK_LITERAL_CONTRADICTION = "RISK_LITERAL_CONTRADICTION"


class ContradictionAnalyzer:
    """Detect only contradictions provable from literal extracted instructions."""

    def __init__(self) -> None:
        self._extractor = DeterministicInstructionExtractor()

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        by_proposition: dict[str, list[InstructionUnit]] = defaultdict(list)
        for document in context.snapshot.documents:
            for rule in self._extractor.extract(document):
                by_proposition[rule.proposition].append(rule)

        findings: list[Finding] = []
        for proposition, rules in by_proposition.items():
            required = [rule for rule in rules if rule.polarity == Polarity.POSITIVE]
            forbidden = [rule for rule in rules if rule.polarity == Polarity.NEGATIVE]
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


def _location(rule: InstructionUnit) -> dict[str, str | None]:
    return {"path": rule.path, "section": rule.section, "rule": rule.text}
