from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai_doc.composition import register_configured_extensions, resolve_token_counter
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.config.models import AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.extensions.process import ProcessExtensionError
from ai_doc.ml.nli_sentence_transformers import SentenceTransformersNLIEngine
from ai_doc.ml.sentence_transformers import LocalModelUnavailableError
from ai_doc.plugins.loader import ExtensionError, load_extensions
from ai_doc.probes.command import CommandTargetProbe, TargetProbeError
from ai_doc.probes.runner import PlanningProbeRunner, compare_planning_reports
from ai_doc.probes.verification import PlanningObservationVerifier
from ai_doc.root import discover_project_root


def probe_command(
    path: Annotated[Path, typer.Argument(help="Repository root to probe.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
    candidate: Annotated[
        Path | None,
        typer.Option(
            "--candidate",
            help="Optional alternate documentation tree for baseline-vs-candidate planning comparison.",
        ),
    ] = None,
) -> None:
    """Run one real target-model planning probe per configured evaluation scenario."""

    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        extensions = load_extensions(project_root, loaded.extensions)
        register_configured_extensions(loaded, extensions)
        token_counter = resolve_token_counter(loaded, extensions)
        baseline = discover_markdown(project_root, loaded, token_counter)
        suite = load_evaluation_suite(project_root)
        probe = CommandTargetProbe()
    except (ConfigError, ExtensionError, ProcessExtensionError, KeyError, ValueError, TargetProbeError, OSError) as exc:
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
        candidate_snapshot = discover_markdown(candidate.resolve(), loaded, token_counter)
        candidate_report = runner.run(candidate_snapshot, suite)
    except (ProcessExtensionError, TargetProbeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(compare_planning_reports(baseline_report, candidate_report).model_dump_json(indent=2))


def _optional_nli_engine(config: AiDocConfig) -> SentenceTransformersNLIEngine | None:
    if not config.local_ml.enabled:
        return None
    try:
        return SentenceTransformersNLIEngine(config.local_ml.nli_model)
    except LocalModelUnavailableError as exc:
        typer.echo(f"Local NLI verification unavailable; using exact planning checks only: {exc}", err=True)
        return None
