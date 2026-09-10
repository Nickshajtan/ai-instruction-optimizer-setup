from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.optimizer.prompt_suboptimizer import PromptOptimizationResult
from ai_doc.optimizer.search import SearchController
from ai_doc.providers.semantic import ProviderUsage
from ai_doc.tokens.counter import ApproximateTokenCounter


class HarmfulPromptSubOptimizer:
    def __init__(self) -> None:
        self.last_usage = ProviderUsage(
            requests=1,
            input_tokens=40,
            output_tokens=10,
            cost_usd="0.001",
        )

    def optimize(self, prompt, evals, budget):
        text = prompt.text.replace("MUST run validation before merge.", "Validation is optional.")
        return PromptOptimizationResult(
            artifact_id=prompt.id,
            optimized_text=text,
            changed=True,
            metadata={"test": "harmful-gepa-rewrite"},
        )


def test_gepa_regression_is_rejected_by_common_invariant_gate(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        "# Rules\n\n<!-- ai-doc:gepa -->\n\nMUST run validation before merge.\n",
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    baseline = discover_markdown(project, config, ApproximateTokenCounter())
    report = run_static_check(project, config)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.CONSERVATIVE)
    runtime.gepa.enabled = True
    runtime.search.max_candidates = 1
    controller = SearchController(
        config,
        runtime,
        tmp_path / "out",
        prompt_suboptimizer=HarmfulPromptSubOptimizer(),
    )
    result = controller.optimize(baseline, EvaluationSuite(), report)
    candidate = next(item for item in result.run.candidates if item.id != "baseline")
    assert candidate.status == "rejected"
    assert any("critical invariant" in reason for reason in candidate.rejection_reasons)
    assert candidate.creation_cost.prompt_suboptimizer_requests == 1
    assert candidate.creation_cost.prompt_suboptimizer_input_tokens == 40
    assert result.run.recommended_candidate_id is None
