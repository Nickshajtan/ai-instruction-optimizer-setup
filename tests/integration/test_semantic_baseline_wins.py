from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationScenario, EvaluationSuite
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
from ai_doc.optimizer.search import SearchController
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_baseline_can_win_against_semantically_valid_candidate(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("# Rules\n\nMUST validate changes.\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["AGENTS.md"]
    config.profiles = {"AGENTS.md": "instruction"}
    baseline = discover_markdown(project, config, ApproximateTokenCounter())
    report = run_static_check(project, config)
    suite = EvaluationSuite(scenarios=[EvaluationScenario(id="validation", task="validate changes")])

    class WorseSemanticGenerator:
        def generate(
            self,
            snapshot,
            _invariants,
            _strategy,
            _previous_summaries,
            _explored_transformations,
            _feedback,
            _memory,
        ):
            text = snapshot.documents[0].text + "\nThis paragraph adds context without changing behavior.\n"
            proposal = CandidateProposal(
                operations=[
                    ProposalOperation(
                        type="rewrite",
                        target="AGENTS.md",
                        reason="semantic expansion",
                        expected_clarity_effect="none",
                        expected_finops_effect="worse",
                        risk="low",
                    )
                ]
            )
            return proposal, {"AGENTS.md": text}

    class PassingEvaluator:
        def evaluate(self, _baseline, _candidate, suite):
            scenario = suite.scenarios[0]
            return EvaluationResult(
                engine="fake-semantic",
                passed=True,
                cases=[EvaluationCaseResult(id=scenario.id, passed=True, score=1.0)],
                raw_summary={"semantic": True},
            )

    runtime = RuntimeSearchConfig(mode=OptimizeMode.BALANCED)
    runtime.population.initial_candidates = 1
    runtime.search.max_candidates = 1
    runtime.search.max_llm_requests = 10
    result = SearchController(
        config,
        runtime,
        tmp_path / "out",
        evaluator=PassingEvaluator(),
        semantic_generator=WorseSemanticGenerator(),
    ).optimize(baseline, suite, report)
    assert result.run.recommended_candidate_id is None
    assert result.run.metadata["baseline_in_frontier"] is True
    assert result.run.recommendation_reason.startswith("baseline/no-change retained")
