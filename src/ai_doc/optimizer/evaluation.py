from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.domain.optimization import CandidateFingerprint, ObjectiveVector, passed_evaluation_score
from ai_doc.reporting.models import CheckReport

EXTRACTED_DOCS_PREFIX = "docs/ai-doc-extracted/"
SECTION_SEPARATOR = "#"
CRITICAL_INVARIANT_FAILURE = "critical invariant recall below 1.0"
REQUIRED_EVALUATION_FAILURE = "required evaluation failed"
NEW_STATIC_ERROR_FAILURE = "new static error introduced"
STATIC_ERROR_FAILURE = "static error present"
CLARITY_CATEGORY = FindingCategory.CLARITY
ERROR_SEVERITY = FindingSeverity.ERROR
WARNING_SEVERITY = FindingSeverity.WARNING
CLARITY_ERROR_WEIGHT = 0.25
CLARITY_WARNING_WEIGHT = 0.05


def fingerprint_candidate(rendered: dict[str, str], operation_types: Sequence[str]) -> CandidateFingerprint:
    digest = hashlib.sha256()
    affected_sections: list[str] = []
    extracted_targets: list[str] = []
    for path in sorted(rendered):
        digest.update(path.encode())
        digest.update(rendered[path].encode())
        if path.startswith(EXTRACTED_DOCS_PREFIX):
            extracted_targets.append(path)
    for op in operation_types:
        if SECTION_SEPARATOR in op:
            affected_sections.append(op)
    return CandidateFingerprint(
        operations=tuple(sorted(operation_types)),
        affected_sections=tuple(sorted(affected_sections)),
        extracted_targets=tuple(sorted(extracted_targets)),
        content_hash=digest.hexdigest(),
    )


def objective_from_report(
    report: CheckReport,
    invariant_regressions: list[str],
    invariant_count: int,
    evaluation: EvaluationResult | None = None,
) -> ObjectiveVector:
    critical_recall = 1.0
    if invariant_count:
        critical_recall = max(0.0, 1.0 - (len(invariant_regressions) / invariant_count))
    clarity_errors = sum(
        1
        for finding in report.findings
        if finding.category == CLARITY_CATEGORY and finding.severity == ERROR_SEVERITY
    )
    clarity_warnings = sum(
        1
        for finding in report.findings
        if finding.category == CLARITY_CATEGORY and finding.severity == WARNING_SEVERITY
    )
    clarity = max(
        0.0,
        1.0 - clarity_errors * CLARITY_ERROR_WEIGHT - clarity_warnings * CLARITY_WARNING_WEIGHT,
    )
    reliability = passed_evaluation_score(evaluation)
    return ObjectiveVector(
        reliability=reliability,
        clarity=clarity,
        always_loaded_tokens=report.context_cost.always_loaded_tokens,
        expected_context_tokens=report.context_cost.estimated_context_tokens,
        estimated_context_cost=report.context_cost.estimated_cost,
        critical_invariant_recall=critical_recall,
    )


def hard_constraint_failures(
    report: CheckReport,
    invariant_regressions: list[str],
    evaluation: EvaluationResult | None,
    baseline_report: CheckReport | None = None,
) -> list[str]:
    failures: list[str] = []
    if invariant_regressions:
        failures.append(CRITICAL_INVARIANT_FAILURE)
    if evaluation and not evaluation.passed:
        failures.append(REQUIRED_EVALUATION_FAILURE)
    static_errors = [finding for finding in report.findings if finding.severity == ERROR_SEVERITY]
    if baseline_report:
        baseline_errors = {(finding.code, finding.path, finding.section) for finding in baseline_report.findings}
        new_errors = [
            finding
            for finding in static_errors
            if (finding.code, finding.path, finding.section) not in baseline_errors
        ]
        if new_errors:
            failures.append(NEW_STATIC_ERROR_FAILURE)
    elif static_errors:
        failures.append(STATIC_ERROR_FAILURE)
    return failures


def finding_subset(report: CheckReport, category: FindingCategory) -> list[Finding]:
    return [finding for finding in report.findings if finding.category == category]


def snapshot_text(snapshot: DocumentationSnapshot) -> str:
    return "\n\n".join(document.text for document in snapshot.documents)
