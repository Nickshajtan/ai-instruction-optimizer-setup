from decimal import Decimal
from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.evaluators.context import ScenarioContextEvaluator
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
        self.calls += 1
        scenarios = payload.get("scenarios", [])
        cases = [
            {"id": scenario["id"], "passed": True, "score": 1.0}
            for scenario in scenarios
            if isinstance(scenario, dict)
        ]
        return SemanticResponse(
            data={"cases": cases},
            usage=ProviderUsage(
                requests=1,
                input_tokens=120,
                output_tokens=10,
                cost_usd=Decimal("0.02"),
            ),
        )


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
    assert result.run.candidates == [result.run.candidates[0]]
    assert result.run.candidates[0].id == "baseline"
