from __future__ import annotations

from dataclasses import dataclass

from ai_doc.config.search import RecommendationConfig
from ai_doc.domain.optimization import Candidate, CandidateStatus, ObjectiveVector


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    objective: ObjectiveVector


class RecommendationPolicy:
    def __init__(self, config: RecommendationConfig | None = None) -> None:
        self.config = config or RecommendationConfig()

    def choose(self, baseline: Candidate, frontier: list[Candidate]) -> Candidate | None:
        if baseline.objective_vector is None:
            baseline.evidence.recommendation_reason = "Baseline has no objective vector; no replacement can be justified."
            return None
        baseline_objective = baseline.objective_vector
        eligible: list[ScoredCandidate] = []
        blocked: list[str] = []
        for candidate in frontier:
            if candidate.id == baseline.id or candidate.objective_vector is None:
                continue
            if candidate.status == CandidateStatus.REJECTED:
                blocked.append(f"{candidate.id}: rejected by safety/evaluation gates")
                continue
            objective = candidate.objective_vector
            reasons = _blocking_reasons(objective, baseline_objective, self.config)
            if reasons:
                blocked.append(f"{candidate.id}: {', '.join(reasons)}")
                continue
            eligible.append(ScoredCandidate(candidate=candidate, objective=objective))
        if not eligible:
            detail = "; ".join(blocked) if blocked else "no generated frontier candidate was eligible"
            baseline.evidence.recommendation_reason = f"No change: {detail}."
            return None
        selected = min(eligible, key=lambda item: item.objective.always_loaded_tokens).candidate
        selected.evidence.recommendation_reason = _selection_reason(
            selected.objective_vector,
            baseline_objective,
            self.config,
        )
        return selected


def _blocking_reasons(
    candidate: ObjectiveVector,
    baseline: ObjectiveVector,
    config: RecommendationConfig,
) -> list[str]:
    reasons: list[str] = []
    if not _reliability_eligible(candidate, baseline, config.minimum_reliability_delta):
        reasons.append(f"reliability delta below {config.minimum_reliability_delta:+.3f}")
    if candidate.clarity - baseline.clarity < config.minimum_clarity_delta:
        reasons.append(f"clarity delta below {config.minimum_clarity_delta:+.3f}")
    if not _material_improvement(candidate, baseline):
        reasons.append("no material objective improvement")
    return reasons


def _selection_reason(
    candidate: ObjectiveVector | None,
    baseline: ObjectiveVector,
    config: RecommendationConfig,
) -> str:
    if candidate is None:
        return "No objective vector available."
    improved = _improved_objectives(candidate, baseline)
    tolerated: list[str] = []
    if candidate.reliability is not None and baseline.reliability is not None:
        delta = candidate.reliability - baseline.reliability
        if delta < 0:
            tolerated.append(f"reliability {delta:+.3f} (limit {config.minimum_reliability_delta:+.3f})")
    clarity_delta = candidate.clarity - baseline.clarity
    if clarity_delta < 0:
        tolerated.append(f"clarity {clarity_delta:+.3f} (limit {config.minimum_clarity_delta:+.3f})")
    improved_text = ", ".join(improved) or "none"
    tolerated_text = ", ".join(tolerated) or "none"
    return f"Recommended: improved objectives={improved_text}; tolerated regressions={tolerated_text}."


def _improved_objectives(candidate: ObjectiveVector, baseline: ObjectiveVector) -> list[str]:
    improved: list[str] = []
    if candidate.reliability is not None and baseline.reliability is not None:
        if candidate.reliability > baseline.reliability:
            improved.append("reliability")
    if candidate.clarity > baseline.clarity:
        improved.append("clarity")
    if candidate.always_loaded_tokens < baseline.always_loaded_tokens:
        improved.append("always_loaded_tokens")
    if _lower_optional(candidate.expected_context_tokens, baseline.expected_context_tokens):
        improved.append("expected_context_tokens")
    if candidate.critical_invariant_recall > baseline.critical_invariant_recall:
        improved.append("critical_invariant_recall")
    return improved


def _reliability_eligible(candidate: ObjectiveVector, baseline: ObjectiveVector, minimum_delta: float) -> bool:
    if candidate.reliability is None and baseline.reliability is None:
        return True
    if candidate.reliability is None or baseline.reliability is None:
        return False
    return candidate.reliability - baseline.reliability >= minimum_delta


def _material_improvement(candidate: ObjectiveVector, baseline: ObjectiveVector) -> bool:
    """Require evidence that replacing the baseline improves at least one optimization objective."""
    return bool(_improved_objectives(candidate, baseline))


def _lower_optional(candidate: float | None, baseline: float | None) -> bool:
    return candidate is not None and baseline is not None and candidate < baseline
