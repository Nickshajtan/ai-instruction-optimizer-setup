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
            return None
        baseline_objective = baseline.objective_vector
        eligible: list[ScoredCandidate] = []
        for candidate in frontier:
            if (
                candidate.id == baseline.id
                or candidate.objective_vector is None
                or candidate.status == CandidateStatus.REJECTED
            ):
                continue
            objective = candidate.objective_vector
            if not _reliability_eligible(objective, baseline_objective, self.config.minimum_reliability_delta):
                continue
            if objective.clarity - baseline_objective.clarity < self.config.minimum_clarity_delta:
                continue
            if not _material_improvement(objective, baseline_objective):
                continue
            eligible.append(ScoredCandidate(candidate=candidate, objective=objective))
        if not eligible:
            return None
        return min(eligible, key=lambda item: item.objective.always_loaded_tokens).candidate


def _reliability_eligible(candidate: ObjectiveVector, baseline: ObjectiveVector, minimum_delta: float) -> bool:
    if candidate.reliability is None and baseline.reliability is None:
        return True
    if candidate.reliability is None or baseline.reliability is None:
        return False
    return candidate.reliability - baseline.reliability >= minimum_delta


def _material_improvement(candidate: ObjectiveVector, baseline: ObjectiveVector) -> bool:
    """Require evidence that replacing the baseline improves at least one optimization objective."""
    if candidate.reliability is not None and baseline.reliability is not None and candidate.reliability > baseline.reliability:
        return True
    return any(
        (
            candidate.clarity > baseline.clarity,
            candidate.always_loaded_tokens < baseline.always_loaded_tokens,
            _lower_optional(candidate.expected_context_tokens, baseline.expected_context_tokens),
            candidate.critical_invariant_recall > baseline.critical_invariant_recall,
        )
    )


def _lower_optional(candidate: float | None, baseline: float | None) -> bool:
    return candidate is not None and baseline is not None and candidate < baseline
