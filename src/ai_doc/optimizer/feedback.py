from __future__ import annotations

from ai_doc.domain.findings import FindingCategory
from ai_doc.domain.optimization import (
    Candidate,
    EvalFailure,
    OptimizationFeedback,
    SearchMemory,
    failed_cases,
)
from ai_doc.optimizer.evaluation import finding_subset
from ai_doc.reporting.models import CheckReport

ROUTER_KEYWORD = "router"
CLARITY_CATEGORY: FindingCategory = "clarity"
FINOPS_CATEGORY: FindingCategory = "finops"


class FeedbackBuilder:
    def build(
        self,
        candidate: Candidate,
        baseline: CheckReport,
        candidate_report: CheckReport,
        frontier: list[Candidate],
    ) -> OptimizationFeedback:
        strengths: list[str] = []
        weaknesses: list[str] = []
        baseline_tokens = baseline.context_cost.always_loaded_tokens
        candidate_tokens = candidate_report.context_cost.always_loaded_tokens
        if candidate_tokens < baseline_tokens:
            reduction = (baseline_tokens - candidate_tokens) / baseline_tokens * 100 if baseline_tokens else 0.0
            strengths.append(f"Reduced always-loaded context by {reduction:.1f}%.")
        if candidate_report.findings:
            weaknesses.append(f"Static analysis reported {len(candidate_report.findings)} findings.")
        if candidate.rejection_reasons:
            weaknesses.extend(candidate.rejection_reasons)
        failed = [
            EvalFailure(scenario_id=case.id, message=case.message, score=case.score)
            for case in failed_cases(candidate.evaluation)
        ]
        directions: list[str] = []
        if any(ROUTER_KEYWORD in (case.message or "").lower() for case in failed):
            directions.append("Retain extraction, but strengthen the root router trigger.")
        if finding_subset(candidate_report, CLARITY_CATEGORY):
            directions.append("Address clarity findings without restoring removed duplicate content.")
        if finding_subset(candidate_report, FINOPS_CATEGORY):
            directions.append("Preserve successful savings and target remaining FinOps findings.")
        return OptimizationFeedback(
            candidate_id=candidate.id,
            strengths=strengths,
            weaknesses=weaknesses,
            failed_evals=failed,
            clarity_findings=finding_subset(candidate_report, CLARITY_CATEGORY),
            finops_findings=finding_subset(candidate_report, FINOPS_CATEGORY),
            invariant_risks=candidate.rejection_reasons,
            comparison_to_baseline=[
                f"Always-loaded tokens: {baseline_tokens} -> {candidate_tokens}."
            ],
            comparison_to_frontier=[f"Compared with {entry.id}." for entry in frontier if entry.id != candidate.id],
            suggested_mutation_directions=directions,
        )


def update_search_memory(memory: SearchMemory, feedback: OptimizationFeedback, entered_frontier: bool) -> SearchMemory:
    if entered_frontier:
        memory.successful_patterns.extend(feedback.strengths)
    else:
        memory.failed_patterns.extend(feedback.weaknesses)
    memory.invariant_risks.extend(feedback.invariant_risks)
    memory.unexplored_opportunities.extend(feedback.suggested_mutation_directions)
    memory.successful_patterns = sorted(set(memory.successful_patterns))
    memory.failed_patterns = sorted(set(memory.failed_patterns))
    memory.invariant_risks = sorted(set(memory.invariant_risks))
    memory.unexplored_opportunities = sorted(set(memory.unexplored_opportunities))
    return memory
