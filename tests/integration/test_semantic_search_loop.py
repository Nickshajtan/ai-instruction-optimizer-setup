from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.optimizer.search import SearchController
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_search_evaluates_failure_builds_feedback_and_repairs_child(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    examples = "".join(f"Example {index}: validate migration behavior carefully.\n" for index in range(180))
    (project / "AGENTS.md").write_text(
        "# Rules\n\n- MUST run validation before completion.\n\n## Migration Examples\n\n" + examples,
        encoding="utf-8",
    )
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md", "docs/**/*.md"]
    config.profiles = {"AGENTS.md": "instruction", "docs/**": "reference"}
    baseline = discover_markdown(project, config, ApproximateTokenCounter())
    baseline_report = run_static_check(project, config)
    suite = EvaluationSuite.model_validate(
        {
            "scenarios": [
                {
                    "id": "migration",
                    "task": "Change and validate migration examples",
                    "expected_required": ["read the migration examples before changing them"],
                }
            ]
        }
    )

    class FakeSemanticEvaluator:
        def evaluate(self, baseline, candidate, suite):
            snapshot = candidate or baseline
            text = "\n".join(document.text for document in snapshot.documents)
            weak_router = "When detailed examples are needed, read" in text
            passed = not weak_router or "MUST read" in text
            message = None if passed else "router too weak to require loading extracted examples"
            scenario_id = suite.scenarios[0].id
            return EvaluationResult(
                engine="fake-semantic",
                passed=passed,
                cases=[
                    EvaluationCaseResult(
                        id=scenario_id,
                        passed=passed,
                        score=1.0 if passed else 0.2,
                        message=message,
                    )
                ],
                raw_summary={"semantic": True},
            )

    runtime = RuntimeSearchConfig(mode=OptimizeMode.SEARCH, seed=7)
    runtime.population.initial_candidates = 1
    runtime.search.generations = 2
    runtime.search.children_per_generation = 1
    runtime.search.max_candidates = 2
    runtime.search.max_llm_requests = 10
    runtime.search.patience = 0
    result = SearchController(config, runtime, tmp_path / "out", evaluator=FakeSemanticEvaluator()).optimize(
        baseline, suite, baseline_report
    )

    generated = [candidate for candidate in result.run.candidates if candidate.id != "baseline"]
    assert len(generated) == 2
    parent, child = generated
    assert parent.status.value == "rejected"
    assert parent.evaluation is not None and parent.evaluation.passed is False
    assert "required evaluation failed" in parent.rejection_reasons
    assert child.parent_ids == [parent.id]
    assert child.evidence.feedback is not None
    assert child.evidence.feedback.failed_evals[0].scenario_id == "migration"
    assert any(operation.type == "strengthen_router" for operation in child.proposal.operations)
    assert child.evaluation is not None and child.evaluation.passed is True
    assert child.objective_vector is not None and child.objective_vector.reliability == 1.0
    assert child.objective_vector.always_loaded_tokens < baseline.total_tokens
    child_tree = Path(child.artifact_dir) / "candidate"
    child_agent = (child_tree / "AGENTS.md").read_text(encoding="utf-8")
    assert "MUST read" in child_agent
    extracted = child_tree / "docs" / "ai-doc-extracted"
    assert any(path.name.endswith("examples.md") for path in extracted.glob("*.md"))
    assert child.creation_cost.evaluation_requests == 1
    assert result.run.total_cost.generation_requests == 0
    assert result.run.recommended_candidate_id == child.id
