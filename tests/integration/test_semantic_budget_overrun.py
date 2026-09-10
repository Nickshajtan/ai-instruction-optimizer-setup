from decimal import Decimal
from pathlib import Path
from typing import cast

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.optimization import SearchMemory
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.invariants import Invariant, InvariantSemanticStatus
from ai_doc.optimizer.prompt_suboptimizer import PromptArtifact, PromptOptimizationResult
from ai_doc.optimizer.search import SearchController
from ai_doc.optimizer.semantic import ProviderSemanticEvaluator
from ai_doc.providers.semantic import (
    BudgetedSemanticProvider,
    ProviderUsage,
    SemanticResponse,
)
from ai_doc.tokens.counter import ApproximateTokenCounter


class OverrunEvaluationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        assert operation == "evaluate"
        self.calls += 1
        scenarios = cast(list[dict[str, object]], payload.get("scenarios", []))
        cases = [{"id": str(scenario["id"]), "passed": True, "score": 1.0} for scenario in scenarios]
        return SemanticResponse(
            data={"cases": cases},
            usage=ProviderUsage(
                requests=1,
                input_tokens=120,
                output_tokens=10,
                cost_usd=Decimal("0.02"),
            ),
        )


class BudgetConsumingGenerator:
    def __init__(self) -> None:
        self.last_usage = ProviderUsage(requests=0)

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        _invariants: list[Invariant],
        _strategy: GenerationStrategyName,
        _previous_summaries: list[str],
        _explored_transformations: list[str],
        _feedback,
        _memory: SearchMemory,
    ) -> tuple[CandidateProposal, dict[str, str]]:
        self.last_usage = ProviderUsage(requests=1, input_tokens=100, output_tokens=10)
        rendered = {document.relative_path: document.text for document in snapshot.documents}
        rendered["AGENTS.md"] += "\n\n<!-- ai-doc:gepa -->\nSemantic candidate.\n"
        return (
            CandidateProposal(
                operations=[
                    ProposalOperation(
                        type="rewrite",
                        target="AGENTS.md",
                        reason="semantic generation for budget-boundary test",
                        expected_clarity_effect="neutral",
                        expected_finops_effect="neutral",
                        risk="low",
                    )
                ]
            ),
            rendered,
        )


class CountingPromptSubOptimizer:
    def __init__(self, input_tokens: int = 0) -> None:
        self.calls = 0
        self.last_usage = ProviderUsage(requests=0)
        self.input_tokens = input_tokens

    def optimize(
        self,
        prompt: PromptArtifact,
        _evals: EvaluationSuite,
        _budget,
    ) -> PromptOptimizationResult:
        self.calls += 1
        self.last_usage = ProviderUsage(requests=1, input_tokens=self.input_tokens, output_tokens=5)
        return PromptOptimizationResult(
            artifact_id=prompt.id,
            optimized_text=prompt.text,
            changed=False,
        )


class CountingInvariantVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, _invariant: Invariant, _candidate: DocumentationSnapshot) -> InvariantSemanticStatus:
        self.calls += 1
        return InvariantSemanticStatus.PRESERVED


def test_one_call_overrun_is_persisted_and_stops_followup_external_work(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse validation.\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    baseline = discover_markdown(tmp_path, config, ApproximateTokenCounter())
    report = run_static_check(tmp_path, config)
    suite = EvaluationSuite(scenarios=[EvaluationScenario(id="validation", task="validate change")])
    inner = OverrunEvaluationProvider()
    provider = BudgetedSemanticProvider(
        inner,
        max_requests=10,
        max_input_tokens=100,
        max_output_tokens=100,
        max_cost_usd=Decimal("1"),
    )
    evaluator = ScenarioContextEvaluator(ProviderSemanticEvaluator(provider))
    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED)
    runtime.search.max_input_tokens = 100
    controller = SearchController(config, runtime, tmp_path / "out", evaluator=evaluator)
    result = controller.optimize(baseline, suite, report)
    assert inner.calls == 1
    assert result.run.total_cost.input_tokens == 120
    assert result.run.stopped_reason == "stopped_token_budget"
    assert len(result.run.candidates) == 1
    assert result.run.candidates[0].id == "baseline"


def test_generation_exhaustion_stops_before_gepa(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nKeep instructions concise.\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    baseline = discover_markdown(tmp_path, config, ApproximateTokenCounter())
    report = run_static_check(tmp_path, config)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.SEARCH)
    runtime.population.initial_candidates = 1
    runtime.search.generations = 2
    runtime.search.children_per_generation = 1
    runtime.search.max_candidates = 2
    runtime.search.max_input_tokens = 100
    runtime.search.patience = 0
    gepa = CountingPromptSubOptimizer()

    result = SearchController(
        config,
        runtime,
        tmp_path / "out",
        semantic_generator=BudgetConsumingGenerator(),
        prompt_suboptimizer=gepa,
    ).optimize(baseline, EvaluationSuite(), report)

    assert result.run.stopped_reason == "stopped_token_budget"
    assert result.run.metadata["budget_stop_stage"] == "semantic candidate generation"
    assert gepa.calls == 0
    assert result.run.total_cost.generation_input_tokens == 100


def test_gepa_exhaustion_stops_before_semantic_invariant_verification(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n<!-- ai-doc:gepa -->\n\nMUST run validation before merge.\n",
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    baseline = discover_markdown(tmp_path, config, ApproximateTokenCounter())
    report = run_static_check(tmp_path, config)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.CONSERVATIVE)
    runtime.search.max_input_tokens = 100
    runtime.gepa.enabled = True
    gepa = CountingPromptSubOptimizer(input_tokens=100)
    verifier = CountingInvariantVerifier()

    result = SearchController(
        config,
        runtime,
        tmp_path / "out",
        semantic_invariant_verifier=verifier,
        prompt_suboptimizer=gepa,
    ).optimize(baseline, EvaluationSuite(), report)

    assert result.run.stopped_reason == "stopped_token_budget"
    assert result.run.metadata["budget_stop_stage"] == "prompt suboptimization"
    assert gepa.calls == 1
    assert verifier.calls == 0
    assert result.run.total_cost.prompt_suboptimizer_input_tokens == 100
