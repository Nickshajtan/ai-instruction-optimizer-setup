from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite, PairwiseOutcome
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.optimizer.semantic import ProviderPairwiseSemanticEvaluator, ProviderSemanticEvaluator
from ai_doc.providers.semantic import ProviderUsage, SemanticResponse
from ai_doc.tokens.counter import ApproximateTokenCounter


class CountingEvaluationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        assert operation == "evaluate"
        self.calls += 1
        scenarios = payload["scenarios"]
        assert isinstance(scenarios, list)
        scenario = scenarios[0]
        assert isinstance(scenario, dict)
        return SemanticResponse(
            data={"cases": [{"id": scenario["id"], "passed": True, "score": 1.0}]},
            usage=ProviderUsage(requests=1, input_tokens=100, output_tokens=20, cost_usd="0.002"),
        )


class PairwiseProvider:
    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        assert operation == "compare_pairwise"
        assert sorted(payload) == [
            "baseline_documents",
            "candidate_documents",
            "dimensions",
            "outcomes",
            "rubric",
            "scenarios",
        ]
        dimensions = payload["dimensions"]
        assert isinstance(dimensions, list)
        return SemanticResponse(
            data={
                "overall": "candidate",
                "reason": "candidate is predicted clearer; not measured target-agent success",
                "dimensions": [
                    {"dimension": dimension, "outcome": "candidate", "evidence": f"{dimension} evidence"}
                    for dimension in dimensions
                ],
            },
            usage=ProviderUsage(requests=1, input_tokens=50, output_tokens=10, cost_usd="0.001"),
        )


def test_scenario_evaluation_usage_is_accumulated_not_last_call_only(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse validation.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    provider = CountingEvaluationProvider()
    semantic = ProviderSemanticEvaluator(provider)
    evaluator = ScenarioContextEvaluator(semantic)
    suite = EvaluationSuite(
        scenarios=[
            EvaluationScenario(id="one", task="validate one"),
            EvaluationScenario(id="two", task="validate two"),
        ]
    )

    result = evaluator.evaluate(snapshot, None, suite)
    usage = semantic.drain_usage()

    assert result.passed is True
    assert provider.calls == 2
    assert usage.requests == 2
    assert usage.input_tokens == 200
    assert usage.output_tokens == 40
    assert str(usage.cost_usd) == "0.004"


def test_provider_pairwise_semantic_evaluator_records_usage(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse validation.\n", encoding="utf-8")
    baseline = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nAlways run validation before merge.\n", encoding="utf-8")
    candidate = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    evaluator = ProviderPairwiseSemanticEvaluator(PairwiseProvider())

    result = evaluator.compare_pairwise(
        baseline,
        candidate,
        EvaluationSuite(scenarios=[EvaluationScenario(id="one", task="validate")]),
    )
    usage = evaluator.drain_usage()

    assert result.overall == PairwiseOutcome.CANDIDATE
    assert all(item.outcome == PairwiseOutcome.CANDIDATE for item in result.dimensions)
    assert "not measured target-agent success" in (result.reason or "")
    assert usage.requests == 1
    assert usage.input_tokens == 50
