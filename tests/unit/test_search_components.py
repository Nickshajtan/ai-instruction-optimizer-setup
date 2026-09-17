from decimal import Decimal
from pathlib import Path

import pytest

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import RecommendationConfig, RuntimeSearchConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationSuite, PairwiseOutcome
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import (
    Candidate,
    CandidateCost,
    ObjectiveVector,
    OptimizationFeedback,
    SearchMemory,
    StopReason,
)
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.domain.scores import ContextCost
from ai_doc.optimizer.evaluation import fingerprint_candidate, hard_constraint_failures
from ai_doc.optimizer.feedback import update_search_memory
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.optimizer.search import PAIRWISE_BUDGET_REJECTION, SearchController, SearchState
from ai_doc.providers.semantic import SemanticBudgetExceeded
from ai_doc.reporting.models import CheckReport


def _report(tokens: int, findings: list[Finding] | None = None) -> CheckReport:
    return CheckReport(
        files_analyzed=1,
        total_tokens=tokens,
        token_counter="approximate",
        context_cost=ContextCost(
            raw_tokens=tokens,
            always_loaded_tokens=tokens,
            referenced_tokens=0,
            duplicate_tokens=0,
        ),
        profiles={"AGENTS.md": "instruction"},
        findings=findings or [],
    )


def _candidate(candidate_id: str, tokens: int, clarity: float = 1.0) -> Candidate:
    return Candidate(
        id=candidate_id,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        objective_vector=ObjectiveVector(
            reliability=1.0,
            clarity=clarity,
            always_loaded_tokens=tokens,
            critical_invariant_recall=1.0,
        ),
        generation=1,
        creation_cost=CandidateCost(total_cost=Decimal("0.25")),
    )


def test_hard_constraint_filters_missing_invariant() -> None:
    assert "critical invariant recall below 1.0" in hard_constraint_failures(
        _report(100), ["inv-1"], None
    )


def test_candidate_fingerprint_deduplicates_identical_content() -> None:
    a = fingerprint_candidate({"AGENTS.md": "same"}, ["rewrite"])
    b = fingerprint_candidate({"AGENTS.md": "same"}, ["rewrite"])
    assert a.content_hash == b.content_hash


def test_recommendation_chooses_lowest_context_within_floors() -> None:
    baseline = _candidate("baseline", 5000, clarity=0.9)
    clarity = _candidate("C001", 4500, clarity=0.95)
    finops = _candidate("C002", 3000, clarity=0.89)
    chosen = RecommendationPolicy(RecommendationConfig()).choose(baseline, [baseline, clarity, finops])
    assert chosen and chosen.id == "C002"


def test_search_memory_records_success_and_failure() -> None:
    memory = SearchMemory()
    feedback = OptimizationFeedback(
        candidate_id="C001",
        strengths=["Reduced always-loaded context by 30.0%."],
        weaknesses=["router failed"],
        invariant_risks=["missing invariant"],
        suggested_mutation_directions=["Retain extraction, but strengthen router."],
    )
    memory = update_search_memory(memory, feedback, entered_frontier=True)
    assert memory.successful_patterns
    memory = update_search_memory(memory, feedback, entered_frontier=False)
    assert memory.failed_patterns


def test_runtime_budget_defaults_are_bounded() -> None:
    runtime = RuntimeSearchConfig()
    assert runtime.search.max_candidates == 4
    assert runtime.search.max_llm_requests == 100


class BudgetExhaustedPairwiseEvaluator:
    def compare_pairwise(self, *_args: object) -> None:
        raise SemanticBudgetExceeded("budget exhausted")


class BrokenPairwiseEvaluator:
    def compare_pairwise(self, *_args: object) -> None:
        raise RuntimeError("provider offline")


def test_pairwise_budget_exhaustion_remains_optional_uncertain(tmp_path: Path) -> None:
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(),
        tmp_path,
        pairwise_semantic_evaluator=BudgetExhaustedPairwiseEvaluator(),
    )
    snapshot = DocumentationSnapshot(root=tmp_path, documents=())

    result, usage = controller._semantic_pairwise(snapshot, snapshot, EvaluationSuite())

    assert result is not None
    assert result.overall == PairwiseOutcome.UNCERTAIN
    assert result.reason == PAIRWISE_BUDGET_REJECTION
    assert usage.requests == 0


def test_pairwise_provider_failure_propagates_operational_error(tmp_path: Path) -> None:
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(),
        tmp_path,
        pairwise_semantic_evaluator=BrokenPairwiseEvaluator(),
    )
    snapshot = DocumentationSnapshot(root=tmp_path, documents=())

    with pytest.raises(RuntimeError, match="provider offline"):
        controller._semantic_pairwise(snapshot, snapshot, EvaluationSuite())


def test_run_reason_uses_recommended_candidate_evidence(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 5000, clarity=0.9)
    candidate = _candidate("C001", 3000, clarity=0.9)
    state = SearchState(candidates=[baseline, candidate], reports={})

    run = SearchController(DEFAULT_CONFIG, RuntimeSearchConfig(), tmp_path)._build_run(
        state,
        baseline,
        StopReason.GENERATION_COMPLETE,
        tmp_path / "run-1",
    )

    assert run.recommended_candidate_id == "C001"
    assert run.recommendation_reason == candidate.evidence.recommendation_reason
    assert "always_loaded_tokens" in (run.recommendation_reason or "")


def test_run_reason_uses_baseline_evidence_when_no_replacement(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 5000, clarity=0.9)
    candidate = _candidate("C001", 5000, clarity=0.9)
    state = SearchState(candidates=[baseline, candidate], reports={})

    run = SearchController(DEFAULT_CONFIG, RuntimeSearchConfig(), tmp_path)._build_run(
        state,
        baseline,
        StopReason.GENERATION_COMPLETE,
        tmp_path / "run-1",
    )

    assert run.recommended_candidate_id is None
    assert run.recommendation_reason == baseline.evidence.recommendation_reason
    assert "no material objective improvement" in (run.recommendation_reason or "")
