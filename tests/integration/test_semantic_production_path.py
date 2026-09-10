import json
import sys
from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.optimizer.search import SearchController
from ai_doc.optimizer.semantic import ProviderPromptSubOptimizer, ProviderSemanticCandidateGenerator, ProviderSemanticEvaluator, ProviderSemanticInvariantService
from ai_doc.providers.semantic import CommandSemanticProvider
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_production_semantic_path_persists_evidence_and_usage(tmp_path: Path) -> None:
    project = tmp_path / "project"; project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n\nValidate migrations before completion.\n\n<!-- ai-doc:gepa -->\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(deep=True); config.include = ["AGENTS.md"]; config.profiles = {"AGENTS.md": "instruction"}
    baseline = discover_markdown(project, config, ApproximateTokenCounter()); report = run_static_check(project, config)
    suite = EvaluationSuite(scenarios=[EvaluationScenario(id="migration", task="validate migration")])
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_semantic_provider.py"
    provider = CommandSemanticProvider(f'"{sys.executable}" "{fixture}"')
    semantic = ProviderSemanticCandidateGenerator(provider); invariants = ProviderSemanticInvariantService(provider)
    evaluator = ScenarioContextEvaluator(ProviderSemanticEvaluator(provider)); gepa = ProviderPromptSubOptimizer(provider)
    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED); runtime.population.initial_candidates = 2; runtime.search.max_candidates = 2
    runtime.search.max_llm_requests = 20; runtime.gepa.enabled = True
    result = SearchController(config, runtime, tmp_path / "out", evaluator=evaluator, semantic_generator=semantic,
        semantic_invariant_verifier=invariants, semantic_invariant_discoverer=invariants, prompt_suboptimizer=gepa).optimize(baseline, suite, report)
    generated = [c for c in result.run.candidates if c.id != "baseline"]
    semantic_candidate = next(c for c in generated if c.creation_cost.generation_requests)
    assert semantic_candidate.creation_cost.generation_input_tokens == 100
    assert semantic_candidate.creation_cost.evaluation_requests == 1
    assert semantic_candidate.creation_cost.prompt_suboptimizer_requests == 1
    assert semantic_candidate.creation_cost.total_cost > 0
    assert any(item.invariant_id == "semantic-critical-1" for item in semantic_candidate.evidence.invariant_decisions)
    assert result.run.metadata["gepa"]["performed"] is True
    assert result.run.recommendation_reason
    evidence_path = Path(semantic_candidate.artifact_dir) / "evidence.json"
    persisted = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert persisted["invariant_decisions"]


def test_context_selector_requires_explicit_router(tmp_path: Path) -> None:
    project = tmp_path / "routing"; (project / "docs").mkdir(parents=True)
    (project / "AGENTS.md").write_text("# Rules\n\nMigration migration migration. [Migration guide](docs/migration.md)\n", encoding="utf-8")
    (project / "docs/migration.md").write_text("# Migration\n\nDetailed migration instructions.\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(deep=True); config.include = ["AGENTS.md", "docs/**/*.md"]
    snapshot = discover_markdown(project, config, ApproximateTokenCounter())
    from ai_doc.evaluators.context import DeterministicContextSelector
    scenario = EvaluationScenario(id="m", task="change migration")
    selected = DeterministicContextSelector().select(snapshot, scenario)
    assert "docs/migration.md" not in {d.relative_path for d in selected.documents}
    (project / "AGENTS.md").write_text("# Rules\n\nWhen changing migration code, MUST read [Migration guide](docs/migration.md).\n", encoding="utf-8")
    snapshot = discover_markdown(project, config, ApproximateTokenCounter())
    selected = DeterministicContextSelector().select(snapshot, scenario)
    assert "docs/migration.md" in {d.relative_path for d in selected.documents}
