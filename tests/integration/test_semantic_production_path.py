import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.cli.optimize import _build_semantic_stack
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.optimization import EvalFailure, OptimizationFeedback, SearchMemory
from ai_doc.evaluators.context import DeterministicContextSelector, ScenarioContextEvaluator
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.search import SearchController
from ai_doc.optimizer.semantic import (
    ProviderPromptSubOptimizer,
    ProviderSemanticCandidateGenerator,
    ProviderSemanticEvaluator,
    ProviderSemanticInvariantService,
)
from ai_doc.providers.semantic import BudgetedSemanticProvider, CommandSemanticProvider
from ai_doc.tokens.counter import ApproximateTokenCounter


def _fixture_command() -> str:
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_semantic_provider.py"
    return f'"{sys.executable}" "{fixture}"'


def test_production_semantic_path_persists_evidence_and_usage(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text(
        "# Rules\n\nValidate migrations before completion.\n\n<!-- ai-doc:gepa -->\n",
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    config.profiles = {"AGENTS.md": "instruction"}
    baseline = discover_markdown(project, config, ApproximateTokenCounter())
    report = run_static_check(project, config)
    suite = EvaluationSuite(scenarios=[EvaluationScenario(id="migration", task="validate migration")])
    provider = CommandSemanticProvider(_fixture_command())
    semantic = ProviderSemanticCandidateGenerator(provider)
    invariants = ProviderSemanticInvariantService(provider)
    evaluator = ScenarioContextEvaluator(ProviderSemanticEvaluator(provider))
    gepa = ProviderPromptSubOptimizer(provider)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED)
    runtime.population.initial_candidates = 2
    runtime.search.max_candidates = 2
    runtime.search.max_llm_requests = 20
    runtime.gepa.enabled = True
    controller = SearchController(
        config,
        runtime,
        tmp_path / "out",
        evaluator=evaluator,
        semantic_generator=semantic,
        semantic_invariant_verifier=invariants,
        semantic_invariant_discoverer=invariants,
        prompt_suboptimizer=gepa,
    )
    result = controller.optimize(baseline, suite, report)
    generated = [candidate for candidate in result.run.candidates if candidate.id != "baseline"]
    semantic_candidate = next(candidate for candidate in generated if candidate.creation_cost.generation_requests)
    assert semantic_candidate.creation_cost.generation_input_tokens == 100
    assert semantic_candidate.creation_cost.evaluation_requests >= 1
    assert semantic_candidate.creation_cost.prompt_suboptimizer_requests == 1
    assert semantic_candidate.creation_cost.total_cost > 0
    assert any(
        item.invariant_id == "semantic-critical-1"
        for item in semantic_candidate.evidence.invariant_decisions
    )
    assert result.run.metadata["gepa"]["performed"] is True
    assert result.run.recommendation_reason
    evidence_path = Path(semantic_candidate.artifact_dir) / "evidence.json"
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["invariant_decisions"]


def test_semantic_discovery_is_conservative_and_preserves_provenance(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nMigration documentation exists.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    service = ProviderSemanticInvariantService(CommandSemanticProvider(_fixture_command()))
    discovered = service.discover(snapshot)
    assert [item.id for item in discovered] == ["semantic-critical-1"]
    invariant = discovered[0]
    assert invariant.discovery_source == "semantic"
    assert invariant.evidence
    assert invariant.rationale


def test_cli_semantic_stack_wires_all_provider_budgets(monkeypatch) -> None:
    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED)
    runtime.search.max_llm_requests = 7
    runtime.search.max_input_tokens = 700
    runtime.search.max_output_tokens = 140
    runtime.search.max_cost_usd = Decimal("0.07")
    monkeypatch.setenv("AI_DOC_SEMANTIC_COMMAND", _fixture_command())
    stack = _build_semantic_stack(runtime, deep=True)
    assert isinstance(stack.provider, BudgetedSemanticProvider)
    assert stack.provider.max_requests == 7
    assert stack.provider.max_input_tokens == 700
    assert stack.provider.max_output_tokens == 140
    assert stack.provider.max_cost_usd == Decimal("0.07")
    assert stack.generator is not None
    assert stack.invariant_verifier is not None
    assert stack.evaluator is not None


def test_production_generator_observes_feedback_and_memory_contents(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse validation.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    generator = ProviderSemanticCandidateGenerator(CommandSemanticProvider(_fixture_command()))
    feedback = OptimizationFeedback(
        candidate_id="C001",
        failed_evals=[EvalFailure(scenario_id="migration", message="router too weak")],
    )
    memory = SearchMemory(failed_patterns=["weak migration router"])
    _, rendered = generator.generate(
        snapshot,
        [],
        GenerationStrategyName.BALANCED,
        previous_summaries=[],
        explored_transformations=[],
        feedback=feedback,
        memory=memory,
    )
    text = rendered["AGENTS.md"]
    assert "router too weak" in text
    assert "weak migration router" in text


def test_context_selector_requires_explicit_router(tmp_path: Path) -> None:
    project = tmp_path / "routing"
    (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text(
        "# Rules\n\nMigration migration migration. [Migration guide](docs/migration.md)\n",
        encoding="utf-8",
    )
    (project / "docs/migration.md").write_text(
        "# Migration\n\nDetailed migration instructions.\n", encoding="utf-8"
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md", "docs/**/*.md"]
    snapshot = discover_markdown(project, config, ApproximateTokenCounter())
    scenario = EvaluationScenario(id="m", task="change migration")
    selected = DeterministicContextSelector().select(snapshot, scenario)
    assert "docs/migration.md" not in {document.relative_path for document in selected.documents}

    (project / "AGENTS.md").write_text(
        "# Rules\n\nWhen changing migration code, MUST read [Migration guide](docs/migration.md).\n",
        encoding="utf-8",
    )
    snapshot = discover_markdown(project, config, ApproximateTokenCounter())
    selected = DeterministicContextSelector().select(snapshot, scenario)
    assert "docs/migration.md" in {document.relative_path for document in selected.documents}
