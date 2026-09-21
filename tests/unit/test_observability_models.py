from __future__ import annotations

from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.domain.evaluations import PairwiseOutcome, PairwiseSemanticResult
from ai_doc.domain.optimization import Candidate, CandidateEvidence, OptimizationRun
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.domain.scores import ContextCost
from ai_doc.observability import ObservationTimer, optimize_observation
from ai_doc.reporting.models import CheckReport, SearchOptimizeReport


def test_pairwise_observation_accounts_for_all_terminal_outcomes(tmp_path: Path) -> None:
    run = OptimizationRun(
        run_id="run-1",
        strategy="balanced",
        pairwise_semantic_requested=True,
        pairwise_comparisons_performed=4,
        candidates=[
            _candidate("baseline", None),
            _candidate("C001", PairwiseOutcome.CANDIDATE),
            _candidate("C002", PairwiseOutcome.BASELINE),
            _candidate("C003", PairwiseOutcome.EQUIVALENT),
            _candidate("C004", PairwiseOutcome.UNCERTAIN),
        ],
        stopped_reason="stopped_generation",
    )
    record = optimize_observation(
        timer=ObservationTimer(),
        root=tmp_path,
        config=DEFAULT_CONFIG,
        report=SearchOptimizeReport(
            baseline=_report(),
            run=run,
            candidates_evaluated=4,
            candidates_rejected=0,
            frontier=[],
            recommended_candidate=None,
            baseline_in_frontier=True,
        ),
        status="completed",
        exit_code=0,
        static_duration_ms=0,
        optimize_duration_ms=0,
    )

    assert record.optimization is not None
    pairwise = record.optimization.pairwise
    assert pairwise is not None
    assert pairwise.candidate_preferred == 1
    assert pairwise.baseline_preferred == 1
    assert pairwise.equivalent == 1
    assert pairwise.uncertain == 1
    assert (
        pairwise.candidate_preferred + pairwise.baseline_preferred + pairwise.equivalent + pairwise.uncertain
    ) == pairwise.comparisons_performed


def _candidate(candidate_id: str, outcome: PairwiseOutcome | None) -> Candidate:
    evidence = CandidateEvidence()
    if outcome is not None:
        evidence.pairwise_semantic = PairwiseSemanticResult(engine="test-pairwise", overall=outcome)
    return Candidate(
        id=candidate_id,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        generation=0,
        evidence=evidence,
    )


def _report() -> CheckReport:
    return CheckReport(
        files_analyzed=1,
        total_tokens=1,
        token_counter="approximate",
        context_cost=ContextCost(
            raw_tokens=1,
            always_loaded_tokens=1,
            referenced_tokens=0,
            duplicate_tokens=0,
        ),
        profiles={"AGENTS.md": "instruction"},
        findings=[],
    )
