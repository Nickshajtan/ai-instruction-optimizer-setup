import sys
from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.optimizer.search import SearchController
from ai_doc.optimizer.semantic import ProviderPromptSubOptimizer
from ai_doc.providers.semantic import CommandSemanticProvider
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_gepa_regression_is_rejected_by_common_invariant_gate(tmp_path: Path, monkeypatch) -> None:
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
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_semantic_provider.py"
    provider = CommandSemanticProvider(f'"{sys.executable}" "{fixture}"')
    monkeypatch.setenv("AI_DOC_TEST_HARMFUL_GEPA", "1")
    controller = SearchController(
        config,
        runtime,
        tmp_path / "out",
        prompt_suboptimizer=ProviderPromptSubOptimizer(provider),
    )
    result = controller.optimize(baseline, EvaluationSuite(), report)
    candidate = next(item for item in result.run.candidates if item.id != "baseline")
    assert candidate.status == "rejected"
    assert any("critical invariant" in reason for reason in candidate.rejection_reasons)
    assert candidate.creation_cost.prompt_suboptimizer_requests == 1
    assert candidate.creation_cost.prompt_suboptimizer_input_tokens == 100
    assert result.run.recommended_candidate_id is None
