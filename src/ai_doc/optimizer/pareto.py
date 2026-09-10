from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ai_doc.config.search import ParetoConfig
from ai_doc.domain.optimization import (
    Candidate,
    CandidateStatus,
    ObjectiveName,
    ObjectiveVector,
    ParetoArchive,
    ParetoEntry,
)


class ObjectiveDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class ObjectiveMetric:
    name: ObjectiveName
    direction: ObjectiveDirection

    def values(self, a: ObjectiveVector, b: ObjectiveVector) -> tuple[float, float] | None:
        raw_a = getattr(a, self.name)
        raw_b = getattr(b, self.name)
        if raw_a is None or raw_b is None:
            return None
        return float(raw_a), float(raw_b)

    def compare(self, a: ObjectiveVector, b: ObjectiveVector, tolerance: float) -> tuple[bool, bool]:
        values = self.values(a, b)
        if values is None:
            return True, False
        av, bv = values
        if self.direction == ObjectiveDirection.MAXIMIZE:
            return av + tolerance >= bv, av > bv + tolerance
        return av <= bv + tolerance, av + tolerance < bv


OBJECTIVE_METRICS: tuple[ObjectiveMetric, ...] = (
    ObjectiveMetric("reliability", ObjectiveDirection.MAXIMIZE),
    ObjectiveMetric("clarity", ObjectiveDirection.MAXIMIZE),
    ObjectiveMetric("critical_invariant_recall", ObjectiveDirection.MAXIMIZE),
    ObjectiveMetric("always_loaded_tokens", ObjectiveDirection.MINIMIZE),
    ObjectiveMetric("expected_context_tokens", ObjectiveDirection.MINIMIZE),
    ObjectiveMetric("estimated_context_cost", ObjectiveDirection.MINIMIZE),
)


def dominates(a: ObjectiveVector, b: ObjectiveVector, tolerances: dict[str, float] | None = None) -> bool:
    tolerances = tolerances or {}
    no_worse = True
    strictly_better = False
    for metric in OBJECTIVE_METRICS:
        metric_no_worse, metric_strictly_better = metric.compare(
            a,
            b,
            tolerances.get(metric.name, 0.0),
        )
        if not metric_no_worse:
            no_worse = False
        if metric_strictly_better:
            strictly_better = True
    return no_worse and strictly_better


class ParetoSelector:
    def __init__(self, config: ParetoConfig | None = None) -> None:
        self.config = config or ParetoConfig()

    def frontier(self, candidates: Sequence[Candidate]) -> list[Candidate]:
        valid = [
            candidate
            for candidate in candidates
            if candidate.objective_vector and candidate.status != CandidateStatus.REJECTED
        ]
        frontier: list[Candidate] = []
        for candidate in valid:
            objective = candidate.objective_vector
            if objective is None:
                continue
            if any(
                other.id != candidate.id
                and other.objective_vector is not None
                and dominates(other.objective_vector, objective, self.config.tolerances)
                for other in valid
            ):
                continue
            frontier.append(candidate)
        return sorted(frontier, key=lambda candidate: candidate.id)


class ParetoArchiveBuilder:
    def __init__(self, selector: ParetoSelector) -> None:
        self.selector = selector

    def build(self, candidates: Sequence[Candidate]) -> ParetoArchive:
        return ParetoArchive(
            entries=[
                ParetoEntry(
                    candidate_id=candidate.id,
                    objective_vector=candidate.objective_vector,
                    generation=candidate.generation,
                    proposal_summary=[operation.type for operation in candidate.proposal.operations],
                    cost=candidate.creation_cost,
                )
                for candidate in self.selector.frontier(candidates)
                if candidate.objective_vector is not None
            ]
        )
