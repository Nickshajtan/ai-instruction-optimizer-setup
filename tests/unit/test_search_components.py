from decimal import Decimal

from ai_doc.config.search import RecommendationConfig, RuntimeSearchConfig
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import Candidate, CandidateCost, ObjectiveVector, OptimizationFeedback, SearchMemory
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.domain.scores import ContextCost
from ai_doc.optimizer.evaluation import fingerprint_candidate, hard_constraint_failures
from ai_doc.optimizer.feedback import update_search_memory
from ai_doc.optimizer.recommendation import RecommendationPolicy
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
