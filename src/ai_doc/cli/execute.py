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
from ai_doc.probes.command import TargetProbeError
from ai_doc.probes.execution import CommandExecutionProbe
from ai_doc.probes.execution_runner import ExecutionActionVerifier, ExecutionProbeRunner
from ai_doc.probes.workspace import UnsafeWorkspaceError
from ai_doc.root import discover_project_root


def execute_command(
    path: Annotated[Path, typer.Argument(help="Repository root to execute against in an isolated copy.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
) -> None:
    """Run one real target-agent execution per configured scenario in a temporary workspace copy."""

    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        extensions = load_extensions(project_root, loaded.extensions)
        register_configured_extensions(loaded, extensions)
        snapshot = discover_markdown(project_root, loaded, resolve_token_counter(loaded, extensions))
        suite = load_evaluation_suite(project_root)
        probe = CommandExecutionProbe()
        verifier = ExecutionActionVerifier(
            _optional_nli_engine(loaded),
            confidence_threshold=loaded.local_ml.nli_confidence_threshold,
        )
        report = ExecutionProbeRunner(probe, verifier).run(snapshot, suite)
    except (
        ConfigError,
        ExtensionError,
        ProcessExtensionError,
        KeyError,
        ValueError,
        TargetProbeError,
        UnsafeWorkspaceError,
        OSError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(report.model_dump_json(indent=2))


def _optional_nli_engine(config: AiDocConfig) -> SentenceTransformersNLIEngine | None:
    if not config.local_ml.enabled:
        return None
    try:
        return SentenceTransformersNLIEngine(config.local_ml.nli_model)
    except LocalModelUnavailableError as exc:
        typer.echo(f"Local NLI verification unavailable; using exact execution checks only: {exc}", err=True)
        return None
