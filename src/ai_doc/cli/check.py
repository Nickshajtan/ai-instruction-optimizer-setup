from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Annotated, Protocol

import typer

from ai_doc.app import has_blocking_static_errors, load_suite, run_static_check
from ai_doc.cli.config_warnings import warn_if_explicit_config_disables_observability
from ai_doc.composition import register_configured_extensions, resolve_configured_evaluator, resolve_token_counter
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.config.models import AiDocConfig, EvaluationEngine, EvaluationModeConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.evaluators.deepeval import DeepEvalEvaluator, DeepEvalUnavailableError
from ai_doc.evaluators.promptfoo import PromptfooEvaluator, PromptfooUnavailableError
from ai_doc.extension_trust import ExtensionTrustError, ensure_extensions_authorized
from ai_doc.extensions.process import ProcessExtensionError
from ai_doc.observability import (
    ObservationRecord,
    ObservationTimer,
    ObservationWriteError,
    append_observation,
    check_observation,
    new_run_id,
)
from ai_doc.optional_dependencies import (
    DependencyStatus,
    OptionalDependencyError,
    install_missing_for_engine,
    missing_dependencies_for_engine,
)
from ai_doc.plugins.loader import ExtensionError, load_extensions
from ai_doc.reporting.console import render_check_console
from ai_doc.reporting.json import render_json
from ai_doc.reporting.models import CheckReport
from ai_doc.root import discover_project_root


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class DeepEvaluator(Protocol):
    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult: ...


def check_command(
    path: Annotated[Path, typer.Argument(help="Repository root to analyze.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
    output_format: Annotated[OutputFormat, typer.Option("--format", help="Output format.")] = OutputFormat.CONSOLE,
    profile: Annotated[DocumentProfile | None, typer.Option("--profile", help="Only analyze one profile.")] = None,
    deep: Annotated[bool, typer.Option("--deep", help="Run external semantic evaluation.")] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Do not prompt before external calls.")
    ] = False,
    install_missing: Annotated[
        bool,
        typer.Option(
            "--install-missing",
            help="Install missing optional dependencies for the configured deep evaluator.",
        ),
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Keep adapter temporary files.")] = False,
    allow_extensions: Annotated[
        bool,
        typer.Option(
            "--allow-extensions",
            help="Execute trusted project-local Python and process extensions declared by repository config.",
        ),
    ] = False,
) -> None:
    timer = ObservationTimer()
    run_id = new_run_id()
    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        warn_if_explicit_config_disables_observability(config, loaded)
        ensure_extensions_authorized(loaded, allow_extensions=allow_extensions)
        extensions = load_extensions(project_root, loaded.extensions, debug=debug)
        register_configured_extensions(loaded, extensions)
        token_counter = resolve_token_counter(loaded, extensions)
        static_started = perf_counter()
        report = run_static_check(project_root, loaded, profile, extensions, token_counter=token_counter)
        static_duration_ms = _elapsed_ms(static_started)
    except (ConfigError, ExtensionTrustError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except (ExtensionError, ProcessExtensionError, KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if deep:
        if not non_interactive:
            typer.echo("Deep mode may run external evaluator/model calls.")
        deep_config = loaded.evaluation.get("deep", EvaluationModeConfig())
        suite = load_suite(project_root)
        try:
            evaluator = resolve_configured_evaluator(loaded, extensions, "deep")
            if evaluator is None:
                _prepare_deep_engine(deep_config.engine, install_missing, non_interactive, output_format)
                evaluator = _deep_evaluator(deep_config.engine, debug, deep_config.model)
            snapshot_report = report
            snapshot = discover_markdown(project_root, loaded, token_counter)
            deep_started = perf_counter()
            report.evaluation = evaluator.evaluate(snapshot, None, suite)
            deep_duration_ms: int | None = _elapsed_ms(deep_started)
        except (PromptfooUnavailableError, DeepEvalUnavailableError, RuntimeError) as exc:
            _safe_append_observation(
                project_root,
                loaded,
                check_observation(
                    run_id=run_id,
                    timer=timer,
                    root=project_root,
                    config=loaded,
                    report=report,
                    status="failed",
                    exit_code=3,
                    static_duration_ms=static_duration_ms,
                ),
            )
            typer.echo(str(exc), err=True)
            raise typer.Exit(3) from exc
        exit_code = 3 if snapshot_report.evaluation and not snapshot_report.evaluation.passed else _exit_code(report)
    else:
        deep_duration_ms = None
        exit_code = _exit_code(report)
    _safe_append_observation(
        project_root,
        loaded,
        check_observation(
            run_id=run_id,
            timer=timer,
            root=project_root,
            config=loaded,
            report=report,
            status="completed",
            exit_code=exit_code,
            static_duration_ms=static_duration_ms,
            deep_duration_ms=deep_duration_ms,
        ),
    )
    typer.echo(render_json(report) if output_format == OutputFormat.JSON else render_check_console(report))
    raise typer.Exit(exit_code)


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _safe_append_observation(project_root: Path, config: AiDocConfig, record: ObservationRecord) -> None:
    try:
        append_observation(project_root, config, record)
    except ObservationWriteError as exc:
        typer.echo(f"Observation logging failed: {exc}", err=True)


def _exit_code(report: CheckReport) -> int:
    return 2 if has_blocking_static_errors(report) else 0


def _prepare_deep_engine(
    engine: EvaluationEngine,
    install_missing: bool,
    non_interactive: bool,
    output_format: OutputFormat,
) -> None:
    missing = missing_dependencies_for_engine(engine)
    if not missing:
        return
    message = _missing_message(missing)
    should_install = install_missing
    if not should_install and not non_interactive and output_format == OutputFormat.CONSOLE:
        should_install = typer.confirm(f"{message}\nInstall missing dependencies now?", default=False)
    if not should_install:
        typer.echo(message, err=True)
        raise typer.Exit(3)
    try:
        installed = install_missing_for_engine(engine)
    except OptionalDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(3) from exc
    if output_format == OutputFormat.CONSOLE:
        typer.echo("Installed optional dependencies:")
        for requirement in installed:
            typer.echo(f"  {requirement}")


def _missing_message(missing: list[DependencyStatus]) -> str:
    lines = ["Missing optional dependencies:"]
    for item in missing:
        lines.append(f"  {item.name}: {item.detail}. {item.install_hint}")
    return "\n".join(lines)


def _deep_evaluator(engine: EvaluationEngine, debug: bool, model: str | None) -> DeepEvaluator:
    if engine == EvaluationEngine.PROMPTFOO:
        return PromptfooEvaluator(debug=debug)
    if engine == EvaluationEngine.DEEPEVAL:
        return DeepEvalEvaluator(model=model)
    raise typer.BadParameter(f"Unsupported deep evaluator: {engine}")
