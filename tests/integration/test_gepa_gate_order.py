from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG, BudgetConfig
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.domain.optimization import SearchMemory
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.invariants import Invariant
from ai_doc.optimizer.prompt_suboptimizer import PromptArtifact, PromptOptimizationResult
from ai_doc.optimizer.search import SearchController
from ai_doc.tokens.counter import ApproximateTokenCounter


class OversizedSemanticGenerator:
    def generate(
        self,
        _snapshot: DocumentationSnapshot,
        _invariants: list[Invariant],
        _strategy: GenerationStrategyName,
        _previous_summaries: list[str],
        _explored_transformations: list[str],
        _feedback,
        _memory: SearchMemory,
    ) -> tuple[CandidateProposal, dict[str, str]]:
        text = "# Rules\n\n<!-- ai-doc:gepa -->\n\n" + ("oversized instruction text " * 200)
        return (
            CandidateProposal(
                operations=[
                    ProposalOperation(
                        type="rewrite",
                        target="AGENTS.md",
                        reason="test oversized semantic candidate",
                        expected_clarity_effect="neutral",
                        expected_finops_effect="worse",
                        risk="high",
                    )
                ]
            ),
            {"AGENTS.md": text},
        )


class CountingPromptSubOptimizer:
    def __init__(self) -> None:
        self.calls = 0

    def optimize(
        self,
        prompt: PromptArtifact,
        _evals: EvaluationSuite,
        _budget,
    ) -> PromptOptimizationResult:
        self.calls += 1
        return PromptOptimizationResult(
            artifact_id=prompt.id,
            optimized_text=prompt.text,
            changed=False,
        )


def test_known_static_failure_does_not_invoke_gepa(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n<!-- ai-doc:gepa -->\n\nKeep this concise.\n",
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    config.budgets[DocumentProfile.INSTRUCTION] = BudgetConfig(error_tokens=80)
    baseline = discover_markdown(tmp_path, config, ApproximateTokenCounter())
    report = run_static_check(tmp_path, config)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED)
    runtime.population.initial_candidates = 2
    runtime.search.max_candidates = 2
    runtime.search.patience = 0
    runtime.gepa.enabled = True
    gepa = CountingPromptSubOptimizer()

    result = SearchController(
        config,
        runtime,
        tmp_path / "out",
        semantic_generator=OversizedSemanticGenerator(),
        prompt_suboptimizer=gepa,
    ).optimize(baseline, EvaluationSuite(), report)

    generated = [candidate for candidate in result.run.candidates if candidate.id != "baseline"]
    assert len(generated) == 2
    assert gepa.calls == 1
    oversized = generated[1]
    assert oversized.status.value == "rejected"
    assert "new static error introduced" in oversized.rejection_reasons
    assert oversized.creation_cost.prompt_suboptimizer_requests == 0
