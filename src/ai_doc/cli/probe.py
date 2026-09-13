from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai_doc.config.loader import ConfigError, load_config
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.ml.nli_sentence_transformers import SentenceTransformersNLIEngine
from ai_doc.ml.sentence_transformers import LocalModelUnavailableError
from ai_doc.probes.command import CommandTargetProbe, TargetProbeError
from ai_doc.probes.runner import PlanningProbeRunner, compare_planning_reports
from ai_doc.probes.verification import PlanningObservationVerifier
from ai_doc.root import discover_project_root
from ai_doc.tokens.counter import ApproximateTokenCounter


def probe_command(
    path: Annotated[Path, typer.Argument(help="Repository root to probe.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
    candidate: Annotated[
        Path | None,
        typer.Option("--candidate", help="Optional alternate documentation tree for baseline-vs-candidate planning comparison."),
    ] = None,
) -> None:
    """Run one real target-model planning probe per configured evaluation scenario."""

    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        baseline = discover_markdown(project_root, loaded, ApproximateTokenCounter())
        suite = load_evaluation_suite(project_root)
        probe = CommandTargetProbe()
    except (ConfigError, TargetProbeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    verifier = PlanningObservationVerifier(
        _optional_nli_engine(loaded),
        confidence_threshold=loaded.local_ml.nli_confidence_threshold,
    )
    runner = PlanningProbeRunner(probe, verifier)
    try:
        baseline_report = runner.run(baseline, suite)
        if candidate is None:
            typer.echo(baseline_report.model_dump_json(indent=2))
            return
        candidate_root = candidate.resolve()
        candidate_snapshot = discover_markdown(candidate_root, loaded, ApproximateTokenCounter())
        candidate_report = runner.run(candidate_snapshot, suite)
    except (TargetProbeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(compare_planning_reports(baseline_report, candidate_report).model_dump_json(indent=2))


def _optional_nli_engine(config: object) -> SentenceTransformersNLIEngine | None:
    local_ml = getattr(config, "local_ml", None)
    if local_ml is None or not local_ml.enabled:
        return None
    try:
        return SentenceTransformersNLIEngine(local_ml.nli_model)
    except LocalModelUnavailableError as exc:
        typer.echo(f"Local NLI verification unavailable; using exact planning checks only: {exc}", err=True)
        return None
