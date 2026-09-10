from decimal import Decimal

from ai_doc.benchmark.models import BenchmarkCase, BenchmarkSuite, BenchmarkVariant, TaskRun
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
    assert report.improved == 1
    assert report.cases[0].task_success_delta.mean_delta == 1.0
    assert report.cases[0].candidate.input_tokens.mean == 800.0


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
