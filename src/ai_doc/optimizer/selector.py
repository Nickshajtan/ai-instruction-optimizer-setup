from __future__ import annotations

from ai_doc.domain.evaluations import CandidateComparison, EvaluationResult, RecommendationDecision
from ai_doc.reporting.models import CheckReport, score_from_report


def compare_candidates(
    baseline: CheckReport,
    candidate: CheckReport,
    invariant_regressions: list[str],
    evaluation: EvaluationResult | None,
) -> CandidateComparison:
    baseline_score = score_from_report(baseline)
    candidate_score = score_from_report(candidate)
    token_delta = candidate_score.total_tokens - baseline_score.total_tokens
    token_delta_percent = (
        (token_delta / baseline_score.total_tokens * 100) if baseline_score.total_tokens else 0.0
    )
    clarity_delta = float(baseline_score.clarity_warnings - candidate_score.clarity_warnings)
    task_success_delta = None
    if evaluation:
        task_success_delta = 0.0 if evaluation.passed else -1.0
    introduced_static_error = (
        candidate_score.structure_errors > baseline_score.structure_errors
        or candidate_score.clarity_errors > baseline_score.clarity_errors
    )
    if invariant_regressions or introduced_static_error or (evaluation and not evaluation.passed):
        recommendation = RecommendationDecision.REJECT
    elif token_delta < 0 and candidate_score.clarity_warnings <= baseline_score.clarity_warnings:
        recommendation = RecommendationDecision.ACCEPT
    else:
        recommendation = RecommendationDecision.REVIEW
    return CandidateComparison(
        baseline=baseline_score,
        candidate=candidate_score,
        clarity_delta=clarity_delta,
        task_success_delta=task_success_delta,
        token_delta=token_delta,
        token_delta_percent=token_delta_percent,
        invariant_regressions=invariant_regressions,
        recommendation=recommendation,
    )
