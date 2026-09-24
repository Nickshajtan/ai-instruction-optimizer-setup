from __future__ import annotations

from decimal import Decimal

from ai_doc.config.models import EvaluationBudgetConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite, Evaluator
from ai_doc.providers.semantic import ProviderUsage, SemanticBudgetExceeded, UsageDrainer

BUDGET_EXHAUSTED_CASE_ID = "budget"
BUDGET_EXHAUSTED_MESSAGE = "External evaluation budget exhausted before starting the next scenario."
BUDGET_EXCEEDED_KEY = "budget_exhausted"
BUDGET_USAGE_KEY = "usage"
BUDGET_UNKNOWN_KEY = "usage_unknown"
UNKNOWN_USAGE_FIELDS = ["input_tokens", "output_tokens", "cost_usd"]


class EvaluationBudget:
    """Track known evaluator usage and block new external calls after exhaustion."""

    def __init__(
        self,
        *,
        max_requests: int | None = None,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
        max_cost_usd: Decimal | None = None,
    ) -> None:
        self.max_requests = max_requests
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_cost_usd = max_cost_usd
        self.usage = ProviderUsage(requests=0, cost_source="unknown")

    @classmethod
    def from_config(cls, config: EvaluationBudgetConfig) -> EvaluationBudget:
        return cls(
            max_requests=config.max_requests,
            max_input_tokens=config.max_input_tokens,
            max_output_tokens=config.max_output_tokens,
            max_cost_usd=config.max_cost_usd,
        )

    def assert_can_start(self) -> None:
        reason = self.exhausted_reason()
        if reason is not None:
            raise SemanticBudgetExceeded(reason)

    def record(self, usage: ProviderUsage) -> None:
        self.usage = ProviderUsage(
            requests=self.usage.requests + usage.requests,
            input_tokens=self.usage.input_tokens + usage.input_tokens,
            output_tokens=self.usage.output_tokens + usage.output_tokens,
            cost_usd=self.usage.cost_usd + usage.cost_usd,
            cost_source=_combine_cost_source(self.usage.cost_source, usage.cost_source),
            cache_hits=self.usage.cache_hits + usage.cache_hits,
        )

    def exhausted_reason(self) -> str | None:
        if self.max_requests is not None and self.usage.requests >= self.max_requests:
            return "external evaluation request budget exhausted"
        if self.max_input_tokens is not None and self.usage.input_tokens >= self.max_input_tokens:
            return "external evaluation input-token budget exhausted"
        if self.max_output_tokens is not None and self.usage.output_tokens >= self.max_output_tokens:
            return "external evaluation output-token budget exhausted"
        if self.max_cost_usd is not None and self.usage.cost_usd >= self.max_cost_usd:
            return "external evaluation cost budget exhausted"
        return None


class BudgetedEvaluator:
    """Apply evaluation budgets at scenario boundaries."""

    def __init__(self, evaluator: Evaluator, budget: EvaluationBudget) -> None:
        self.evaluator = evaluator
        self.budget = budget

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        cases: list[EvaluationCaseResult] = []
        raw_summaries: list[dict[str, object]] = []
        engine: str | None = None
        semantic = False
        budget_exhausted = False
        exhaustion_message: str | None = None
        for scenario in suite.scenarios:
            try:
                self.budget.assert_can_start()
            except SemanticBudgetExceeded as exc:
                budget_exhausted = True
                exhaustion_message = str(exc)
                break
            result = self.evaluator.evaluate(baseline, candidate, EvaluationSuite(scenarios=[scenario]))
            engine = result.engine
            semantic = semantic or bool(result.raw_summary.get("semantic"))
            raw_summaries.append(result.raw_summary)
            usage = _result_usage(result)
            if isinstance(self.evaluator, UsageDrainer):
                usage = self.evaluator.drain_usage()
            self.budget.record(usage)
            cases.extend(result.cases or [EvaluationCaseResult(id=scenario.id, passed=result.passed)])
            exhaustion_message = self.budget.exhausted_reason()
            if exhaustion_message is not None:
                budget_exhausted = True
                break

        if budget_exhausted:
            cases.append(
                EvaluationCaseResult(
                    id=BUDGET_EXHAUSTED_CASE_ID,
                    passed=False,
                    message=exhaustion_message or BUDGET_EXHAUSTED_MESSAGE,
                )
            )
        if not suite.scenarios:
            result = self.evaluator.evaluate(baseline, candidate, suite)
            result.raw_summary = {
                **result.raw_summary,
                BUDGET_EXCEEDED_KEY: False,
                BUDGET_USAGE_KEY: self.budget.usage.model_dump(mode="json"),
            }
            return result

        return EvaluationResult(
            engine=engine or str(getattr(self.evaluator, "engine", self.evaluator.__class__.__name__)),
            passed=bool(cases) and all(case.passed for case in cases),
            cases=cases,
            raw_summary={
                "semantic": semantic,
                BUDGET_EXCEEDED_KEY: budget_exhausted,
                BUDGET_USAGE_KEY: self.budget.usage.model_dump(mode="json"),
                BUDGET_UNKNOWN_KEY: _unknown_usage_fields(raw_summaries),
                "scenario_results": len([case for case in cases if case.id != BUDGET_EXHAUSTED_CASE_ID]),
            },
        )


def _result_usage(result: EvaluationResult) -> ProviderUsage:
    raw = result.raw_summary.get(BUDGET_USAGE_KEY)
    if isinstance(raw, dict):
        return ProviderUsage.model_validate(raw)
    return ProviderUsage(requests=1, cost_source="unknown")


def _unknown_usage_fields(summaries: list[dict[str, object]]) -> list[str]:
    unknown: set[str] = set()
    for summary in summaries:
        fields = summary.get(BUDGET_UNKNOWN_KEY)
        if isinstance(fields, list):
            unknown.update(str(field) for field in fields)
    return sorted(unknown) if unknown else UNKNOWN_USAGE_FIELDS


def _combine_cost_source(current: str, new: str) -> str:
    if current == new:
        return current
    if current == "unknown":
        return new
    if new == "unknown":
        return current
    return "mixed"
