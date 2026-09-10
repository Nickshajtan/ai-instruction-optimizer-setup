from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.optimizer.semantic import ProviderSemanticEvaluator
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
