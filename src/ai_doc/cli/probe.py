from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai_doc.cli.config_warnings import warn_if_explicit_config_disables_observability
from ai_doc.composition import register_configured_extensions, resolve_token_counter
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.config.models import AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.extension_trust import ExtensionTrustError, ensure_extensions_authorized
from ai_doc.extensions.process import ProcessExtensionError
from ai_doc.ml.nli_sentence_transformers import SentenceTransformersNLIEngine
from ai_doc.ml.sentence_transformers import LocalModelUnavailableError
from ai_doc.observability import (
    ObservationRecord,
    ObservationTimer,
    ObservationWriteError,
    append_observation,
    new_run_id,
    probe_observation,
)
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
    allow_extensions: Annotated[
        bool,
        typer.Option(
            "--allow-extensions",
            help="Execute trusted project-local Python and process extensions declared by repository config.",
        ),
    ] = False,
) -> None:
    """Run one real target-model planning probe per configured evaluation scenario."""

    timer = ObservationTimer()
    run_id = new_run_id()
    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        warn_if_explicit_config_disables_observability(config, loaded)
        ensure_extensions_authorized(loaded, allow_extensions=allow_extensions)
        extensions = load_extensions(project_root, loaded.extensions)
        register_configured_extensions(loaded, extensions)
        token_counter = resolve_token_counter(loaded, extensions)
        baseline = discover_markdown(project_root, loaded, token_counter)
        suite = load_evaluation_suite(project_root)
        probe = CommandTargetProbe()
    except (
        ConfigError,
        ExtensionTrustError,
        ExtensionError,
        ProcessExtensionError,
        KeyError,
        ValueError,
        TargetProbeError,
        OSError,
    ) as exc:
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
            _safe_append_observation(
                project_root,
                loaded,
                probe_observation(
                    run_id=run_id,
                    timer=timer,
                    root=project_root,
                    config=loaded,
                    command="probe",
                    status="completed",
                    exit_code=0,
                    document_count=len(baseline.documents),
                    scenario_count=len(suite.scenarios),
                ),
            )
            typer.echo(baseline_report.model_dump_json(indent=2))
            return
        candidate_snapshot = discover_markdown(candidate.resolve(), loaded, token_counter)
        candidate_report = runner.run(candidate_snapshot, suite)
    except (ProcessExtensionError, TargetProbeError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    _safe_append_observation(
        project_root,
        loaded,
        probe_observation(
            run_id=run_id,
            timer=timer,
            root=project_root,
            config=loaded,
            command="probe",
            status="completed",
            exit_code=0,
            document_count=len(baseline.documents),
            scenario_count=len(suite.scenarios),
        ),
    )
    typer.echo(compare_planning_reports(baseline_report, candidate_report).model_dump_json(indent=2))


def _safe_append_observation(project_root: Path, config: AiDocConfig, record: ObservationRecord) -> None:
    try:
        append_observation(project_root, config, record)
    except ObservationWriteError as exc:
        typer.echo(f"Observation logging failed: {exc}", err=True)


def _optional_nli_engine(config: AiDocConfig) -> SentenceTransformersNLIEngine | None:
    if not config.local_ml.enabled:
        return None
    try:
        return SentenceTransformersNLIEngine(config.local_ml.nli_model)
    except LocalModelUnavailableError as exc:
        typer.echo(f"Local NLI verification unavailable; using exact planning checks only: {exc}", err=True)
        return None
