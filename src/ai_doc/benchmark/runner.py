from __future__ import annotations

from collections.abc import Callable
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


def evaluate_benchmark(
    suite: BenchmarkSuite,
    *,
    minimum_meaningful_improvement: float = 0.05,
    minimum_runs: int = 3,
) -> BenchmarkReport:
    reports = [
        _evaluate_case(
            case,
            minimum_meaningful_improvement=minimum_meaningful_improvement,
            minimum_runs=minimum_runs,
        )
        for case in suite.cases
    ]
    return BenchmarkReport(
        minimum_meaningful_improvement=minimum_meaningful_improvement,
        minimum_runs=minimum_runs,
        cases=reports,
        improved=sum(item.decision == BenchmarkDecision.IMPROVED for item in reports),
        regressed=sum(item.decision == BenchmarkDecision.REGRESSED for item in reports),
        inconclusive=sum(item.decision == BenchmarkDecision.INCONCLUSIVE for item in reports),
    )


def _evaluate_case(
    case: BenchmarkCase,
    *,
    minimum_meaningful_improvement: float,
    minimum_runs: int,
) -> BenchmarkCaseReport:
    baseline_runs = [run for run in case.runs if run.variant == BenchmarkVariant.BASELINE]
    candidate_runs = [run for run in case.runs if run.variant == BenchmarkVariant.CANDIDATE]
    success_delta = _paired_delta(baseline_runs, candidate_runs, lambda run: float(run.success))
    decision, reason = _decision(
        success_delta,
        minimum_meaningful_improvement=minimum_meaningful_improvement,
        minimum_runs=minimum_runs,
    )
    return BenchmarkCaseReport(
        id=case.id,
        repository=case.repository,
        task=case.task,
        agents=sorted({run.metadata.agent for run in case.runs}),
        baseline=_variant_summary(baseline_runs),
        candidate=_variant_summary(candidate_runs),
        task_success_delta=success_delta,
        instruction_violations_delta=_paired_delta(
            baseline_runs,
            candidate_runs,
            lambda run: float(run.instruction_violations),
        ),
        retries_delta=_paired_delta(baseline_runs, candidate_runs, lambda run: float(run.retries)),
        input_tokens_delta=_paired_delta(baseline_runs, candidate_runs, lambda run: float(run.input_tokens)),
        output_tokens_delta=_paired_delta(baseline_runs, candidate_runs, lambda run: float(run.output_tokens)),
        latency_ms_delta=_paired_optional_delta(baseline_runs, candidate_runs, lambda run: run.latency_ms),
        cost_usd_delta=_paired_optional_delta(
            baseline_runs,
            candidate_runs,
            lambda run: float(run.cost_usd) if run.cost_usd is not None else None,
        ),
        score_delta=_paired_optional_delta(baseline_runs, candidate_runs, lambda run: run.score),
        decision=decision,
        decision_reason=reason,
    )


def _paired_delta(
    baseline: list[TaskRun],
    candidate: list[TaskRun],
    value: Callable[[TaskRun], float],
) -> DeltaEvidence:
    paired = min(len(baseline), len(candidate))
    deltas = [value(candidate[index]) - value(baseline[index]) for index in range(paired)]
    return _delta_evidence(deltas)


def _paired_optional_delta(
    baseline: list[TaskRun],
    candidate: list[TaskRun],
    value: Callable[[TaskRun], float | None],
) -> DeltaEvidence | None:
    paired = min(len(baseline), len(candidate))
    deltas: list[float] = []
    for index in range(paired):
        baseline_value = value(baseline[index])
        candidate_value = value(candidate[index])
        if baseline_value is not None and candidate_value is not None:
            deltas.append(candidate_value - baseline_value)
    return _delta_evidence(deltas) if deltas else None


def _delta_evidence(deltas: list[float]) -> DeltaEvidence:
    if not deltas:
        return DeltaEvidence(
            mean_delta=0.0,
            median_delta=0.0,
            stddev=0.0,
            ci95_low=0.0,
            ci95_high=0.0,
            paired_samples=0,
        )
    delta_mean = mean(deltas)
    stddev = pstdev(deltas) if len(deltas) > 1 else 0.0
    margin = 1.96 * stddev / sqrt(len(deltas)) if len(deltas) > 1 else 0.0
    return DeltaEvidence(
        mean_delta=delta_mean,
        median_delta=median(deltas),
        stddev=stddev,
        ci95_low=delta_mean - margin,
        ci95_high=delta_mean + margin,
        paired_samples=len(deltas),
    )


def _decision(
    delta: DeltaEvidence,
    *,
    minimum_meaningful_improvement: float,
    minimum_runs: int,
) -> tuple[BenchmarkDecision, str]:
    if delta.paired_samples < minimum_runs:
        return BenchmarkDecision.INCONCLUSIVE, f"need at least {minimum_runs} paired runs"
    if delta.ci95_low >= minimum_meaningful_improvement:
        return BenchmarkDecision.IMPROVED, "task-success improvement is larger than the configured noise threshold"
    if delta.ci95_high <= -minimum_meaningful_improvement:
        return BenchmarkDecision.REGRESSED, "task-success regression is larger than the configured noise threshold"
    return BenchmarkDecision.INCONCLUSIVE, "observed task-success delta overlaps the configured noise threshold"


def _variant_summary(runs: list[TaskRun]) -> VariantSummary:
    return VariantSummary(
        runs=len(runs),
        task_success=_metric([float(run.success) for run in runs]),
        instruction_violations=_metric([float(run.instruction_violations) for run in runs]),
        retries=_metric([float(run.retries) for run in runs]),
        input_tokens=_metric([float(run.input_tokens) for run in runs]),
        output_tokens=_metric([float(run.output_tokens) for run in runs]),
        latency_ms=_optional_metric([run.latency_ms for run in runs]),
        cost_usd=_optional_metric([float(run.cost_usd) if run.cost_usd is not None else None for run in runs]),
        score=_optional_metric([run.score for run in runs]),
    )


def _metric(values: list[float]) -> MetricSummary:
    if not values:
        return MetricSummary(samples=0, mean=0.0, median=0.0, stddev=0.0)
    return MetricSummary(
        samples=len(values),
        mean=mean(values),
        median=median(values),
        stddev=pstdev(values) if len(values) > 1 else 0.0,
    )


def _optional_metric(values: list[float | None]) -> MetricSummary | None:
    present = [value for value in values if value is not None]
    return _metric(present) if present else None
