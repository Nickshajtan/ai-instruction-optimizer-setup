from ai_doc.domain.evaluations import PairwiseOutcome, PairwiseSemanticResult
from ai_doc.domain.optimization import Candidate, CandidateStatus, ObjectiveVector
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.recommendation import RecommendationPolicy


def _candidate(candidate_id: str, objective: ObjectiveVector) -> Candidate:
    return Candidate(
        id=candidate_id,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        objective_vector=objective,
        status=CandidateStatus.FRONTIER,
        generation=0 if candidate_id == "baseline" else 1,
    )


def test_recommended_candidate_records_improvements_and_tolerated_regressions() -> None:
    baseline = _candidate(
        "baseline",
        ObjectiveVector(
            reliability=1.0,
            clarity=0.9,
            always_loaded_tokens=1000,
            expected_context_tokens=800,
            critical_invariant_recall=1.0,
        ),
    )
    candidate = _candidate(
        "C001",
        ObjectiveVector(
            reliability=0.995,
            clarity=0.9,
            always_loaded_tokens=700,
            expected_context_tokens=650,
            critical_invariant_recall=1.0,
        ),
    )
    assert RecommendationPolicy().choose(baseline, [baseline, candidate]) is candidate
    reason = candidate.evidence.recommendation_reason or ""
    assert "always_loaded_tokens" in reason
    assert "expected_context_tokens" in reason
    assert "reliability -0.005" in reason


def test_no_change_records_concrete_blocking_factor() -> None:
    baseline = _candidate(
        "baseline",
        ObjectiveVector(
            reliability=1.0,
            clarity=0.9,
            always_loaded_tokens=1000,
            expected_context_tokens=800,
            critical_invariant_recall=1.0,
        ),
    )
    candidate = _candidate(
        "C001",
        ObjectiveVector(
            reliability=1.0,
            clarity=0.9,
            always_loaded_tokens=1000,
            expected_context_tokens=800,
            critical_invariant_recall=1.0,
        ),
    )
    assert RecommendationPolicy().choose(baseline, [baseline, candidate]) is None
    assert "C001: no material objective improvement" in (baseline.evidence.recommendation_reason or "")


def test_pairwise_candidate_prediction_can_supply_transparent_b_tier_improvement() -> None:
    objective = ObjectiveVector(
        reliability=1.0,
        clarity=0.9,
        always_loaded_tokens=1000,
        expected_context_tokens=800,
        critical_invariant_recall=1.0,
    )
    baseline = _candidate("baseline", objective)
    candidate = _candidate("C001", objective)
    candidate.evidence.pairwise_semantic = PairwiseSemanticResult(
        engine="test",
        overall=PairwiseOutcome.CANDIDATE,
        reason="candidate predicted clearer; not empirical target-agent performance",
    )

    assert RecommendationPolicy().choose(baseline, [baseline, candidate]) is candidate
    assert "pairwise semantic=candidate predicted better" in (candidate.evidence.recommendation_reason or "")


def test_uncertain_pairwise_prediction_does_not_block_or_create_improvement() -> None:
    objective = ObjectiveVector(
        reliability=1.0,
        clarity=0.9,
        always_loaded_tokens=1000,
        expected_context_tokens=800,
        critical_invariant_recall=1.0,
    )
    baseline = _candidate("baseline", objective)
    candidate = _candidate("C001", objective)
    candidate.evidence.pairwise_semantic = PairwiseSemanticResult(
        engine="test",
        overall=PairwiseOutcome.UNCERTAIN,
        reason="insufficient evidence",
    )

    assert RecommendationPolicy().choose(baseline, [baseline, candidate]) is None
    assert "C001: no material objective improvement" in (baseline.evidence.recommendation_reason or "")


def test_negative_pairwise_prediction_does_not_veto_objective_improvement() -> None:
    baseline = _candidate(
        "baseline",
        ObjectiveVector(
            reliability=1.0,
            clarity=0.9,
            always_loaded_tokens=1000,
            expected_context_tokens=800,
            critical_invariant_recall=1.0,
        ),
    )
    candidate = _candidate(
        "C001",
        ObjectiveVector(
            reliability=1.0,
            clarity=0.9,
            always_loaded_tokens=700,
            expected_context_tokens=800,
            critical_invariant_recall=1.0,
        ),
    )
    candidate.evidence.pairwise_semantic = PairwiseSemanticResult(
        engine="test",
        overall=PairwiseOutcome.BASELINE,
        reason="baseline predicted better",
    )

    assert RecommendationPolicy().choose(baseline, [baseline, candidate]) is candidate
    assert "always_loaded_tokens" in (candidate.evidence.recommendation_reason or "")
