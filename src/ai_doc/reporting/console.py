from __future__ import annotations

from collections import Counter

from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.domain.optimization import ObjectiveVector
from ai_doc.reporting.models import CheckReport, OptimizeReport, SearchOptimizeReport

TOP_FINDING_LIMIT = 10


def render_check_console(report: CheckReport) -> str:
    by_category = Counter(f.category for f in report.findings)
    by_severity = Counter(f.severity for f in report.findings)
    lines = _check_summary_lines(report)
    lines.extend(_finding_summary_lines(by_category, by_severity))
    lines.extend(_top_finding_lines(report.findings))
    if report.evaluation:
        lines.extend(_evaluation_lines(report))
    return "\n".join(lines).rstrip() + "\n"


def render_optimize_console(report: OptimizeReport) -> str:
    comparison = report.comparison
    lines = [
        "AI Documentation Optimization Report",
        "",
        f"Baseline tokens: {comparison.baseline.total_tokens:,}",
        f"Candidate tokens: {comparison.candidate.total_tokens:,}",
        f"Token delta: {comparison.token_delta:,} ({comparison.token_delta_percent:.1f}%)",
        f"Always-loaded tokens: {comparison.baseline.always_loaded_tokens:,} -> {comparison.candidate.always_loaded_tokens:,}",
        f"Invariant regressions: {len(comparison.invariant_regressions)}",
        f"Recommendation: {comparison.recommendation.upper()}",
        "",
        f"Proposal: {report.proposal_path}",
        f"Candidate: {report.candidate_path}",
        f"Diff: {report.diff_path}",
    ]
    return "\n".join(lines) + "\n"


def render_search_optimize_console(report: SearchOptimizeReport, show_frontier: bool = False) -> str:
    baseline_vector = _baseline_objective_vector(report)
    lines = [
        "AI Documentation Optimization",
        "",
        "Baseline:",
        *_objective_vector_lines(baseline_vector, include_token_unit=True),
        "",
        f"Candidates evaluated: {report.candidates_evaluated}",
        f"Candidates rejected:   {report.candidates_rejected}",
        f"Pareto frontier:       {len(report.frontier)}",
        f"Stop reason:           {report.run.stopped_reason}",
    ]
    if report.baseline_in_frontier:
        lines.append("Baseline remains on the Pareto frontier.")
    if show_frontier or report.frontier:
        lines.extend(["", "Frontier"])
        for entry in report.frontier:
            lines.extend(
                [
                    f"{entry.candidate_id} - {', '.join(entry.proposal_summary) or 'baseline'}",
                    *_objective_vector_lines(entry.objective_vector),
                ]
            )
    lines.extend(
        ["", "Recommended:", f"  {report.run.recommended_candidate_id or 'none'}", "", "Source repository unchanged."]
    )
    return "\n".join(lines) + "\n"


def _check_summary_lines(report: CheckReport) -> list[str]:
    return [
        "AI Documentation Report",
        "",
        f"Files analyzed: {report.files_analyzed}",
        f"Total tokens: {report.total_tokens:,} ({report.token_counter})",
        f"Always-loaded tokens: {report.context_cost.always_loaded_tokens:,}",
        f"Duplicate tokens: {report.context_cost.duplicate_tokens:,}",
        "",
    ]


def _finding_summary_lines(by_category: Counter[FindingCategory], by_severity: Counter[FindingSeverity]) -> list[str]:
    return [
        "Findings",
        f"  Errors: {by_severity[FindingSeverity.ERROR]}",
        f"  Warnings: {by_severity[FindingSeverity.WARNING]}",
        f"  Clarity: {by_category[FindingCategory.CLARITY]}",
        f"  FinOps: {by_category[FindingCategory.FINOPS]}",
        f"  Structure: {by_category[FindingCategory.STRUCTURE]}",
        "",
    ]


def _top_finding_lines(findings: list[Finding]) -> list[str]:
    lines = ["Top findings"]
    for finding in findings[:TOP_FINDING_LIMIT]:
        section = f"#{finding.section}" if finding.section else ""
        lines.extend(
            [
                f"[{finding.category.upper()}:{finding.severity.upper()}] {finding.path}{section}",
                f"{finding.code}: {finding.message}",
            ]
        )
        if finding.suggestion:
            lines.append(f"Suggestion: {finding.suggestion}")
        lines.append("")
    return lines


def _evaluation_lines(report: CheckReport) -> list[str]:
    if report.evaluation is None:
        return []
    return ["Evaluation", f"  Engine: {report.evaluation.engine}", f"  Passed: {report.evaluation.passed}"]


def _baseline_objective_vector(report: SearchOptimizeReport) -> ObjectiveVector:
    return next(
        candidate.objective_vector
        for candidate in report.run.candidates
        if candidate.id == "baseline" and candidate.objective_vector is not None
    )


def _objective_vector_lines(vector: ObjectiveVector, include_token_unit: bool = False) -> list[str]:
    token_suffix = " tokens" if include_token_unit else ""
    reliability = "not evaluated" if vector.reliability is None else f"{vector.reliability:.2f}"
    return [
        f"  reliability:         {reliability}",
        f"  clarity:             {vector.clarity:.2f}",
        f"  always-loaded:       {vector.always_loaded_tokens:,}{token_suffix}",
    ]
