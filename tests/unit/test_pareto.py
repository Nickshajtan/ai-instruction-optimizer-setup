from ai_doc.config.search import ParetoConfig
from ai_doc.domain.optimization import Candidate, CandidateStatus, ObjectiveVector
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.pareto import ParetoArchiveBuilder, ParetoSelector, dominates


def _candidate(
    candidate_id: str,
    reliability: float,
    clarity: float,
    tokens: int,
    status: CandidateStatus = CandidateStatus.VALID,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        objective_vector=ObjectiveVector(
            reliability=reliability,
            clarity=clarity,
            always_loaded_tokens=tokens,
            critical_invariant_recall=1.0,
        ),
        status=status,
        generation=1,
    )


def test_competing_clarity_and_token_candidates_both_remain() -> None:
    a = _candidate("A", 1.0, 0.9, 5000)
    b = _candidate("B", 1.0, 0.8, 4000)
    frontier = ParetoSelector(ParetoConfig(tolerances={})).frontier([a, b])
    assert {candidate.id for candidate in frontier} == {"A", "B"}


def test_candidate_dominates_when_no_worse_and_strictly_better() -> None:
    a = ObjectiveVector(
        reliability=0.95,
        clarity=0.90,
        always_loaded_tokens=4000,
        critical_invariant_recall=1.0,
    )
    b = ObjectiveVector(
        reliability=0.94,
        clarity=0.88,
        always_loaded_tokens=4500,
        critical_invariant_recall=1.0,
    )
    assert dominates(a, b)


def test_tolerance_prevents_noise_dominance() -> None:
    a = ObjectiveVector(
        reliability=0.95,
        clarity=0.901,
        always_loaded_tokens=4000,
        critical_invariant_recall=1.0,
    )
    b = ObjectiveVector(
        reliability=0.95,
        clarity=0.900,
        always_loaded_tokens=4000,
        critical_invariant_recall=1.0,
    )
    assert not dominates(a, b, {"clarity": 0.01})


def test_selector_uses_configured_tolerance_when_building_frontier() -> None:
    a = _candidate("A", 1.0, 0.95, 4000)
    b = _candidate("B", 1.0, 0.90, 4000)
    selector = ParetoSelector(ParetoConfig(tolerances={"clarity": 0.10}))

    frontier = selector.frontier([a, b])

    assert {candidate.id for candidate in frontier} == {"A", "B"}


def test_archive_removes_dominated_candidate() -> None:
    a = _candidate("A", 0.95, 0.90, 4000)
    b = _candidate("B", 0.94, 0.88, 4500)
    archive = ParetoArchiveBuilder(ParetoSelector(ParetoConfig(tolerances={}))).build([a, b])
    assert [entry.candidate_id for entry in archive.entries] == ["A"]


def test_rejected_candidate_cannot_enter_frontier() -> None:
    c = _candidate("C", 1.0, 0.95, 2000, status=CandidateStatus.REJECTED)
    assert ParetoSelector().frontier([c]) == []
