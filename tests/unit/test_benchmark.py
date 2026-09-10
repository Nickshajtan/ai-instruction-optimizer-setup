from decimal import Decimal

import pytest

from ai_doc.benchmark.models import BenchmarkCase, BenchmarkDecision, BenchmarkSuite, BenchmarkVariant, TaskRun
from ai_doc.benchmark.runner import evaluate_benchmark


def _run(run_id: str, variant: BenchmarkVariant, success: bool, tokens: int, cost: str) -> TaskRun:
    return TaskRun(
        run_id=run_id,
        variant=variant,
        success=success,
        input_tokens=tokens,
        output_tokens=100,
        cost_usd=Decimal(cost),
    )


def test_benchmark_marks_clear_improvement() -> None:
    case = BenchmarkCase(
        id="task-1",
        repository="example/repo",
        task="Implement a safe change",
        runs=[
            _run("b1", BenchmarkVariant.BASELINE, False, 1000, "0.10"),
            _run("b2", BenchmarkVariant.BASELINE, False, 1000, "0.10"),
            _run("b3", BenchmarkVariant.BASELINE, False, 1000, "0.10"),
            _run("c1", BenchmarkVariant.CANDIDATE, True, 800, "0.08"),
            _run("c2", BenchmarkVariant.CANDIDATE, True, 800, "0.08"),
            _run("c3", BenchmarkVariant.CANDIDATE, True, 800, "0.08"),
        ],
    )
    report = evaluate_benchmark(BenchmarkSuite(cases=[case]), minimum_meaningful_improvement=0.05)
    item = report.cases[0]
    assert report.improved == 1
    assert item.task_success_delta.mean_delta == 1.0
    assert item.candidate.input_tokens.mean == 800.0
    assert item.candidate.input_tokens.median == 800.0
    assert item.input_tokens_delta.mean_delta == -200.0
    assert item.cost_usd_delta is not None
    assert item.cost_usd_delta.mean_delta == pytest.approx(-0.02)
    assert not report.has_regressions


def test_benchmark_is_inconclusive_when_runs_are_insufficient() -> None:
    case = BenchmarkCase(
        id="task-1",
        repository="example/repo",
        task="Implement a safe change",
        runs=[
            _run("b1", BenchmarkVariant.BASELINE, False, 1000, "0.10"),
            _run("c1", BenchmarkVariant.CANDIDATE, True, 800, "0.08"),
        ],
    )
    report = evaluate_benchmark(BenchmarkSuite(cases=[case]), minimum_runs=3)
    assert report.inconclusive == 1
    assert "paired runs" in report.cases[0].decision_reason


def test_benchmark_marks_clear_task_regression() -> None:
    case = BenchmarkCase(
        id="task-1",
        repository="example/repo",
        task="Implement a safe change",
        runs=[
            _run("b1", BenchmarkVariant.BASELINE, True, 1000, "0.10"),
            _run("b2", BenchmarkVariant.BASELINE, True, 1000, "0.10"),
            _run("b3", BenchmarkVariant.BASELINE, True, 1000, "0.10"),
            _run("c1", BenchmarkVariant.CANDIDATE, False, 700, "0.07"),
            _run("c2", BenchmarkVariant.CANDIDATE, False, 700, "0.07"),
            _run("c3", BenchmarkVariant.CANDIDATE, False, 700, "0.07"),
        ],
    )
    report = evaluate_benchmark(BenchmarkSuite(cases=[case]))
    assert report.regressed == 1
    assert report.has_regressions
    assert report.cases[0].decision == BenchmarkDecision.REGRESSED
