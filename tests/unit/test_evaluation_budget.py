from __future__ import annotations

from decimal import Decimal

from ai_doc.config.models import EvaluationBudgetConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.evaluators.budget import BudgetedEvaluator, EvaluationBudget
from ai_doc.providers.semantic import ProviderUsage


def _snapshot() -> DocumentationSnapshot:
    return DocumentationSnapshot.model_validate(
        {
            "root": ".",
            "documents": [
                {
                    "path": "AGENTS.md",
                    "relative_path": "AGENTS.md",
                    "profile": "instruction",
                    "text": "Run validation.",
                    "token_count": 2,
                }
            ],
        }
    )


def _suite(count: int) -> EvaluationSuite:
    return EvaluationSuite.model_validate(
        {"scenarios": [{"id": f"s{index}", "task": "Validate."} for index in range(count)]}
    )


class UsageEvaluator:
    def __init__(self, usages: list[ProviderUsage]) -> None:
        self.usages = usages
        self.calls = 0
        self.last_usage = ProviderUsage(requests=0, cost_source="unknown")

    def evaluate(self, _baseline, _candidate, suite):
        scenario = suite.scenarios[0]
        usage = self.usages[self.calls]
        self.calls += 1
        self.last_usage = usage
        return EvaluationResult(
            engine="fake",
            passed=True,
            cases=[EvaluationCaseResult(id=scenario.id, passed=True)],
            raw_summary={"semantic": True, "usage": usage.model_dump(mode="json")},
        )

    def drain_usage(self) -> ProviderUsage:
        usage = self.last_usage
        self.last_usage = ProviderUsage(requests=0, cost_source="unknown")
        return usage


def test_budgeted_evaluator_stops_after_request_budget_exhaustion() -> None:
    evaluator = UsageEvaluator([ProviderUsage(requests=1), ProviderUsage(requests=1)])
    budgeted = BudgetedEvaluator(evaluator, EvaluationBudget.from_config(EvaluationBudgetConfig(max_requests=1)))

    result = budgeted.evaluate(_snapshot(), None, _suite(3))

    assert evaluator.calls == 1
    assert result.passed is False
    assert [case.id for case in result.cases] == ["s0", "budget"]
    assert result.raw_summary["budget_exhausted"] is True
    assert result.raw_summary["usage"]["requests"] == 1


def test_budgeted_evaluator_enforces_input_output_and_cost_budgets() -> None:
    budgets = [
        EvaluationBudgetConfig(max_input_tokens=5),
        EvaluationBudgetConfig(max_output_tokens=3),
        EvaluationBudgetConfig(max_cost_usd=Decimal("0.01")),
    ]
    usages = [
        ProviderUsage(requests=1, input_tokens=5),
        ProviderUsage(requests=1, output_tokens=3),
        ProviderUsage(requests=1, cost_usd=Decimal("0.01"), cost_source="estimated"),
    ]

    for config, usage in zip(budgets, usages, strict=True):
        evaluator = UsageEvaluator([usage, usage])
        result = BudgetedEvaluator(evaluator, EvaluationBudget.from_config(config)).evaluate(
            _snapshot(), None, _suite(2)
        )

        assert evaluator.calls == 1
        assert result.cases[-1].id == "budget"
        assert result.raw_summary["budget_exhausted"] is True


def test_budgeted_evaluator_preserves_one_call_overrun_before_stopping() -> None:
    evaluator = UsageEvaluator(
        [
            ProviderUsage(requests=1, input_tokens=10),
            ProviderUsage(requests=1, input_tokens=1),
        ]
    )
    budgeted = BudgetedEvaluator(evaluator, EvaluationBudget.from_config(EvaluationBudgetConfig(max_input_tokens=5)))

    result = budgeted.evaluate(_snapshot(), None, _suite(2))

    assert evaluator.calls == 1
    assert result.raw_summary["usage"]["input_tokens"] == 10
    assert [case.id for case in result.cases] == ["s0", "budget"]
    assert result.raw_summary["budget_exhausted"] is True


def test_budgeted_evaluator_reports_single_scenario_overrun() -> None:
    evaluator = UsageEvaluator([ProviderUsage(requests=1, input_tokens=10)])
    budgeted = BudgetedEvaluator(evaluator, EvaluationBudget.from_config(EvaluationBudgetConfig(max_input_tokens=5)))

    result = budgeted.evaluate(_snapshot(), None, _suite(1))

    assert evaluator.calls == 1
    assert result.raw_summary["usage"]["input_tokens"] == 10
    assert result.raw_summary["budget_exhausted"] is True
    assert [case.id for case in result.cases] == ["s0", "budget"]


def test_budgeted_evaluator_reports_exact_single_scenario_exhaustion() -> None:
    evaluator = UsageEvaluator([ProviderUsage(requests=1)])
    budgeted = BudgetedEvaluator(evaluator, EvaluationBudget.from_config(EvaluationBudgetConfig(max_requests=1)))

    result = budgeted.evaluate(_snapshot(), None, _suite(1))

    assert evaluator.calls == 1
    assert result.raw_summary["usage"]["requests"] == 1
    assert result.raw_summary["budget_exhausted"] is True
    assert [case.id for case in result.cases] == ["s0", "budget"]


def test_budgeted_evaluator_marks_unknown_usage_honestly() -> None:
    class UnknownUsageEvaluator:
        def evaluate(self, _baseline, _candidate, suite):
            return EvaluationResult(
                engine="opaque",
                passed=True,
                cases=[EvaluationCaseResult(id=suite.scenarios[0].id, passed=True)],
                raw_summary={"semantic": True},
            )

    result = BudgetedEvaluator(
        UnknownUsageEvaluator(),
        EvaluationBudget.from_config(EvaluationBudgetConfig(max_requests=2)),
    ).evaluate(_snapshot(), None, _suite(1))

    assert result.raw_summary["usage"]["requests"] == 1
    assert result.raw_summary["usage"]["cost_source"] == "unknown"
    assert set(result.raw_summary["usage_unknown"]) == {"input_tokens", "output_tokens", "cost_usd"}
