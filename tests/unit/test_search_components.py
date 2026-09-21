from decimal import Decimal
from pathlib import Path

import pytest

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import RecommendationConfig, RuntimeSearchConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import (
    EvaluationResult,
    EvaluationScenario,
    EvaluationSuite,
    PairwiseExecutionDisposition,
    PairwiseOutcome,
    PairwiseSemanticResult,
)
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
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
from ai_doc.optimizer.search import (
    PAIRWISE_BUDGET_REJECTION,
    CandidateDraft,
    CandidateWorkspace,
    EvaluationContext,
    SearchController,
    SearchState,
)
from ai_doc.providers.semantic import ProviderUsage, SemanticBudgetExceeded
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


class CountingPairwiseEvaluator:
    def __init__(self, outcome: PairwiseOutcome = PairwiseOutcome.CANDIDATE) -> None:
        self.calls = 0
        self.outcome = outcome

    def compare_pairwise(self, *_args: object) -> PairwiseSemanticResult:
        self.calls += 1
        return PairwiseSemanticResult(engine="test-pairwise", overall=self.outcome)


class FailingEvaluator:
    def evaluate(self, *_args: object) -> EvaluationResult:
        return EvaluationResult(engine="test", passed=False)


def _search_context(tmp_path: Path, baseline: Candidate, baseline_tokens: int = 1000) -> EvaluationContext:
    snapshot = DocumentationSnapshot(root=tmp_path, documents=())
    return EvaluationContext(snapshot, baseline, EvaluationSuite(), _report(baseline_tokens), [], 0, tmp_path)


def _search_context_with_scenario(tmp_path: Path, baseline: Candidate) -> EvaluationContext:
    snapshot = DocumentationSnapshot(root=tmp_path, documents=())
    suite = EvaluationSuite(scenarios=[EvaluationScenario(id="case", task="follow the rules")])
    return EvaluationContext(snapshot, baseline, suite, _report(1000), [], 0, tmp_path)


def _draft(parent: Candidate) -> CandidateDraft:
    return CandidateDraft(
        candidate_id="C001",
        generation=1,
        parent=parent,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        rendered={"AGENTS.md": "# Candidate\n"},
        source=DocumentationSnapshot(root=Path("."), documents=()),
        feedback=None,
        generation_usage=ProviderUsage(requests=0),
        gepa_usage=ProviderUsage(requests=0),
    )


def _workspace(tmp_path: Path, tokens: int, findings: list[Finding] | None = None) -> CandidateWorkspace:
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir(exist_ok=True)
    return CandidateWorkspace(
        candidate_dir=candidate_dir,
        diff_path=tmp_path / "diff.patch",
        report=_report(tokens, findings),
        snapshot=DocumentationSnapshot(root=tmp_path, documents=()),
    )


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


def test_gated_pairwise_disabled_preserves_optional_pairwise_execution(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    evaluator = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=False),
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context_with_scenario(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert evaluator.calls == 1
    assert candidate.evidence.pairwise_semantic is not None
    assert candidate.evidence.pairwise_semantic_disposition == PairwiseExecutionDisposition.PERFORMED


def test_gated_pairwise_skips_when_objective_evidence_is_sufficient(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    evaluator = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context_with_scenario(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert evaluator.calls == 0
    assert candidate.evidence.pairwise_semantic is None
    assert candidate.evidence.pairwise_semantic_disposition == PairwiseExecutionDisposition.SKIPPED_NOT_NEEDED
    run = controller._build_run(
        SearchState(candidates=[baseline, candidate], reports={}),
        baseline,
        StopReason.PATIENCE,
        tmp_path,
    )
    assert run.pairwise_comparisons_performed == 0
    assert run.pairwise_comparisons_skipped_not_needed == 1


def test_gated_pairwise_runs_when_material_improvement_needs_pairwise(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=1.0)
    evaluator = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 1000, []),
        [],
    )

    assert evaluator.calls == 1
    assert candidate.evidence.pairwise_semantic is not None
    assert candidate.evidence.pairwise_semantic_disposition == PairwiseExecutionDisposition.PERFORMED
    assert controller._pairwise_comparisons_performed == 1


def test_required_pairwise_overrides_optional_gate(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    evaluator = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, require_pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert evaluator.calls == 1
    assert candidate.evidence.pairwise_semantic_disposition == PairwiseExecutionDisposition.PERFORMED


def test_static_rejection_does_not_mark_pairwise_not_needed(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    evaluator = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )
    finding = Finding(
        code="x-error",
        category=FindingCategory.RISK,
        severity=FindingSeverity.ERROR,
        path="AGENTS.md",
        message="new error",
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, [finding]),
        [],
    )

    assert evaluator.calls == 0
    assert candidate.status == "rejected"
    assert candidate.evidence.pairwise_semantic_disposition is None


def test_semantic_evaluation_rejection_does_not_mark_pairwise_not_needed(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=1.0)
    pairwise = CountingPairwiseEvaluator()
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
        evaluator=FailingEvaluator(),
        pairwise_semantic_evaluator=pairwise,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context_with_scenario(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert pairwise.calls == 0
    assert candidate.status == "rejected"
    assert candidate.evidence.pairwise_semantic_disposition is None


def test_unavailable_pairwise_is_not_marked_not_needed(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    controller = SearchController(
        DEFAULT_CONFIG,
        RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True),
        tmp_path,
    )

    candidate, _, _ = controller._evaluate_candidate(
        _draft(baseline),
        _search_context(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert candidate.evidence.pairwise_semantic is None
    assert candidate.evidence.pairwise_semantic_disposition is None


def test_budget_blocked_pairwise_is_not_marked_not_needed(tmp_path: Path) -> None:
    baseline = _candidate("baseline", 1000, clarity=0.9)
    evaluator = CountingPairwiseEvaluator()
    runtime = RuntimeSearchConfig(pairwise_semantic=True, gated_pairwise=True)
    runtime.search.max_llm_requests = 0
    controller = SearchController(
        DEFAULT_CONFIG,
        runtime,
        tmp_path,
        pairwise_semantic_evaluator=evaluator,
    )

    candidate, _, stop = controller._evaluate_candidate(
        _draft(baseline),
        _search_context(tmp_path, baseline),
        set(),
        _workspace(tmp_path, 500, []),
        [],
    )

    assert stop == StopReason.REQUEST_BUDGET
    assert evaluator.calls == 0
    assert candidate.evidence.pairwise_semantic_disposition is None


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
