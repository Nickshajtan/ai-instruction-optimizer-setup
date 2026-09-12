from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import sqrt
from statistics import mean, median, pstdev

from ai_doc.benchmark.models import (
    BenchmarkCase,
    BenchmarkCaseReport,
    BenchmarkDecision,
    BenchmarkReport,
    BenchmarkSuite,
    BenchmarkVariant,
    DeltaEvidence,
    MetricSummary,
    TaskRun,
    VariantSummary,
)


@dataclass(frozen=True)
class RunPair:
    baseline: TaskRun
    candidate: TaskRun


class RunPairer:
    """Pair baseline and candidate runs, preferring explicit pair IDs when available."""

    def pair(self, baseline: Sequence[TaskRun], candidate: Sequence[TaskRun]) -> list[RunPair]:
        if self._has_explicit_pairs(baseline, candidate):
            return self._pair_by_id(baseline, candidate)
        paired = min(len(baseline), len(candidate))
        return [RunPair(baseline[index], candidate[index]) for index in range(paired)]

    @staticmethod
    def _has_explicit_pairs(baseline: Sequence[TaskRun], candidate: Sequence[TaskRun]) -> bool:
        runs = [*baseline, *candidate]
        return bool(runs) and all(run.pair_id is not None for run in runs)

    @staticmethod
    def _pair_by_id(baseline: Sequence[TaskRun], candidate: Sequence[TaskRun]) -> list[RunPair]:
        baseline_by_id = {run.pair_id: run for run in baseline if run.pair_id is not None}
        candidate_by_id = {run.pair_id: run for run in candidate if run.pair_id is not None}
        common_ids = sorted(baseline_by_id.keys() & candidate_by_id.keys())
        return [RunPair(baseline_by_id[pair_id], candidate_by_id[pair_id]) for pair_id in common_ids]


class BenchmarkStatistics:
    """Calculate summaries and paired-delta evidence independently of benchmark policy."""

    def metric(self, values: Sequence[float]) -> MetricSummary:
        if not values:
            return MetricSummary(samples=0, mean=0.0, median=0.0, stddev=0.0)
        return MetricSummary(
            samples=len(values),
            mean=mean(values),
            median=median(values),
            stddev=pstdev(values) if len(values) > 1 else 0.0,
        )

    def optional_metric(self, values: Sequence[float | None]) -> MetricSummary | None:
        present = [value for value in values if value is not None]
        return self.metric(present) if present else None

    def delta(self, values: Sequence[float]) -> DeltaEvidence:
        if not values:
            return DeltaEvidence(
                mean_delta=0.0,
                median_delta=0.0,
                stddev=0.0,
                ci95_low=0.0,
                ci95_high=0.0,
                paired_samples=0,
            )
        delta_mean = mean(values)
        stddev = pstdev(values) if len(values) > 1 else 0.0
        margin = 1.96 * stddev / sqrt(len(values)) if len(values) > 1 else 0.0
        return DeltaEvidence(
            mean_delta=delta_mean,
            median_delta=median(values),
            stddev=stddev,
            ci95_low=delta_mean - margin,
            ci95_high=delta_mean + margin,
            paired_samples=len(values),
        )


@dataclass(frozen=True)
class BenchmarkDecisionPolicy:
    minimum_meaningful_improvement: float = 0.05
    minimum_runs: int = 3

    def decide(self, delta: DeltaEvidence) -> tuple[BenchmarkDecision, str]:
        if delta.paired_samples < self.minimum_runs:
            return BenchmarkDecision.INCONCLUSIVE, f"need at least {self.minimum_runs} paired runs"
        if delta.ci95_low >= self.minimum_meaningful_improvement:
            return BenchmarkDecision.IMPROVED, "task-success improvement is larger than the configured noise threshold"
        if delta.ci95_high <= -self.minimum_meaningful_improvement:
            return BenchmarkDecision.REGRESSED, "task-success regression is larger than the configured noise threshold"
        return BenchmarkDecision.INCONCLUSIVE, "observed task-success delta overlaps the configured noise threshold"


class BenchmarkCaseEvaluator:
    def __init__(
        self,
        *,
        statistics: BenchmarkStatistics | None = None,
        pairer: RunPairer | None = None,
        decision_policy: BenchmarkDecisionPolicy | None = None,
    ) -> None:
        self.statistics = statistics or BenchmarkStatistics()
        self.pairer = pairer or RunPairer()
        self.decision_policy = decision_policy or BenchmarkDecisionPolicy()

    def evaluate(self, case: BenchmarkCase) -> BenchmarkCaseReport:
        baseline_runs = [run for run in case.runs if run.variant == BenchmarkVariant.BASELINE]
        candidate_runs = [run for run in case.runs if run.variant == BenchmarkVariant.CANDIDATE]
        pairs = self.pairer.pair(baseline_runs, candidate_runs)
        success_delta = self._paired_delta(pairs, lambda run: float(run.success))
        decision, reason = self.decision_policy.decide(success_delta)
        return BenchmarkCaseReport(
            id=case.id,
            repository=case.repository,
            task=case.task,
            agents=sorted({run.metadata.agent for run in case.runs}),
            baseline=self._variant_summary(baseline_runs),
            candidate=self._variant_summary(candidate_runs),
            task_success_delta=success_delta,
            instruction_violations_delta=self._paired_delta(pairs, lambda run: float(run.instruction_violations)),
            retries_delta=self._paired_delta(pairs, lambda run: float(run.retries)),
            input_tokens_delta=self._paired_delta(pairs, lambda run: float(run.input_tokens)),
            output_tokens_delta=self._paired_delta(pairs, lambda run: float(run.output_tokens)),
            latency_ms_delta=self._paired_optional_delta(pairs, lambda run: run.latency_ms),
            cost_usd_delta=self._paired_optional_delta(
                pairs,
                lambda run: float(run.cost_usd) if run.cost_usd is not None else None,
            ),
            score_delta=self._paired_optional_delta(pairs, lambda run: run.score),
            decision=decision,
            decision_reason=reason,
        )

    def _paired_delta(self, pairs: Sequence[RunPair], value: Callable[[TaskRun], float]) -> DeltaEvidence:
        deltas = [value(pair.candidate) - value(pair.baseline) for pair in pairs]
        return self.statistics.delta(deltas)

    def _paired_optional_delta(
        self,
        pairs: Sequence[RunPair],
        value: Callable[[TaskRun], float | None],
    ) -> DeltaEvidence | None:
        deltas: list[float] = []
        for pair in pairs:
            baseline_value = value(pair.baseline)
            candidate_value = value(pair.candidate)
            if baseline_value is not None and candidate_value is not None:
                deltas.append(candidate_value - baseline_value)
        return self.statistics.delta(deltas) if deltas else None

    def _variant_summary(self, runs: Sequence[TaskRun]) -> VariantSummary:
        return VariantSummary(
            runs=len(runs),
            task_success=self.statistics.metric([float(run.success) for run in runs]),
            instruction_violations=self.statistics.metric([float(run.instruction_violations) for run in runs]),
            retries=self.statistics.metric([float(run.retries) for run in runs]),
            input_tokens=self.statistics.metric([float(run.input_tokens) for run in runs]),
            output_tokens=self.statistics.metric([float(run.output_tokens) for run in runs]),
            latency_ms=self.statistics.optional_metric([run.latency_ms for run in runs]),
            cost_usd=self.statistics.optional_metric(
                [float(run.cost_usd) if run.cost_usd is not None else None for run in runs]
            ),
            score=self.statistics.optional_metric([run.score for run in runs]),
        )


class BenchmarkEvaluator:
    def __init__(self, case_evaluator: BenchmarkCaseEvaluator) -> None:
        self.case_evaluator = case_evaluator

    @classmethod
    def default(
        cls,
        *,
        minimum_meaningful_improvement: float = 0.05,
        minimum_runs: int = 3,
    ) -> BenchmarkEvaluator:
        policy = BenchmarkDecisionPolicy(
            minimum_meaningful_improvement=minimum_meaningful_improvement,
            minimum_runs=minimum_runs,
        )
        return cls(BenchmarkCaseEvaluator(decision_policy=policy))

    def evaluate(self, suite: BenchmarkSuite) -> BenchmarkReport:
        reports = [self.case_evaluator.evaluate(case) for case in suite.cases]
        policy = self.case_evaluator.decision_policy
        return BenchmarkReport(
            minimum_meaningful_improvement=policy.minimum_meaningful_improvement,
            minimum_runs=policy.minimum_runs,
            cases=reports,
            improved=sum(item.decision == BenchmarkDecision.IMPROVED for item in reports),
            regressed=sum(item.decision == BenchmarkDecision.REGRESSED for item in reports),
            inconclusive=sum(item.decision == BenchmarkDecision.INCONCLUSIVE for item in reports),
        )


def evaluate_benchmark(
    suite: BenchmarkSuite,
    *,
    minimum_meaningful_improvement: float = 0.05,
    minimum_runs: int = 3,
) -> BenchmarkReport:
    """Stable facade for benchmark aggregation and decision policy."""
    evaluator = BenchmarkEvaluator.default(
        minimum_meaningful_improvement=minimum_meaningful_improvement,
        minimum_runs=minimum_runs,
    )
    return evaluator.evaluate(suite)
