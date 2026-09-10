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
        eligible: list[ScoredCandidate] = []
        baseline_objective = baseline.objective_vector
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
