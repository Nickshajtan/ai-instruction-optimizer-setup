from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from ai_doc.domain.evaluations import CandidateComparison, EvaluationResult
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import Candidate, OptimizationRun, ParetoEntry
from ai_doc.domain.scores import ContextCost, ScoreSet


class FindingAuditEvent(BaseModel):
    adapter: str
    code: str
    severity: str
    path: str
    section: str | None = None
    action: str


class FindingAudit(BaseModel):
    builtin_error_count: int = 0
    adapter_events: list[FindingAuditEvent] = Field(default_factory=list)


class CheckReport(BaseModel):
    files_analyzed: int
    total_tokens: int
    token_counter: str
    token_count_accuracy: str = "unknown"
    context_cost: ContextCost
    profiles: dict[str, str]
    findings: list[Finding]
    finding_audit: FindingAudit = Field(default_factory=FindingAudit)
    evaluation: EvaluationResult | None = None


class OptimizeReport(BaseModel):
    baseline: CheckReport
    candidate: CheckReport
    comparison: CandidateComparison
    proposal_path: str
    candidate_path: str
    diff_path: str
    invariant_regressions: list[str]


class SearchOptimizeReport(BaseModel):
    baseline: CheckReport
    run: OptimizationRun
    candidates_evaluated: int
    candidates_rejected: int
    frontier: list[ParetoEntry]
    recommended_candidate: Candidate | None
    baseline_in_frontier: bool


class ReportScoringStrategy(Protocol):
    def score(self, report: CheckReport) -> ScoreSet:
        ...


class StaticFindingScoringStrategy:
    def score(self, report: CheckReport) -> ScoreSet:
        return ScoreSet(
            clarity_errors=self._count_findings(report, category="clarity", severity="error"),
            clarity_warnings=self._count_findings(report, category="clarity", severity="warning"),
            finops_warnings=self._count_findings(report, category="finops", severity="warning"),
            structure_errors=self._count_findings(report, category="structure", severity="error"),
            total_tokens=report.total_tokens,
            always_loaded_tokens=report.context_cost.always_loaded_tokens,
            duplicate_tokens=report.context_cost.duplicate_tokens,
        )

    def _count_findings(self, report: CheckReport, category: str, severity: str) -> int:
        return sum(1 for finding in report.findings if finding.category == category and finding.severity == severity)


DEFAULT_SCORING_STRATEGY = StaticFindingScoringStrategy()


def score_from_report(
    report: CheckReport,
    strategy: ReportScoringStrategy = DEFAULT_SCORING_STRATEGY,
) -> ScoreSet:
    return strategy.score(report)
