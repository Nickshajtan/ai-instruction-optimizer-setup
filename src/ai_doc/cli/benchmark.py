from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai_doc.benchmark.models import BenchmarkSuite
from ai_doc.benchmark.runner import evaluate_benchmark
from ai_doc.reporting.json import render_json


def benchmark_command(
    evidence: Annotated[Path, typer.Argument(help="Benchmark evidence JSON file.")],
    minimum_meaningful_improvement: Annotated[
        float,
        typer.Option(
            "--minimum-meaningful-improvement",
            min=0.0,
            help="Minimum task-success delta treated as meaningful.",
        ),
    ] = 0.05,
    minimum_runs: Annotated[
        int,
        typer.Option("--minimum-runs", min=1, help="Minimum paired runs required for a conclusive decision."),
    ] = 3,
    fail_on_regression: Annotated[
        bool,
        typer.Option("--fail-on-regression", help="Exit with code 5 when a meaningful task regression is detected."),
    ] = False,
) -> None:
    """Summarize baseline vs candidate agent-task evidence with variance-aware decisions."""
    try:
        suite = BenchmarkSuite.model_validate_json(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        typer.echo(f"Invalid benchmark evidence: {exc}", err=True)
        raise typer.Exit(1) from exc
    report = evaluate_benchmark(
        suite,
        minimum_meaningful_improvement=minimum_meaningful_improvement,
        minimum_runs=minimum_runs,
    )
    typer.echo(render_json(report))
    if fail_on_regression and report.has_regressions:
        raise typer.Exit(5)
