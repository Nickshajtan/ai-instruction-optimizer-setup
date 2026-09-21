from __future__ import annotations

from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.reporting.models import CheckReport
from ai_doc.tokens.counter import TokenCounter

DEFAULT_OPTIMIZER_OUTPUT_ROOT = ".ai-doc-output"


def optimization_source_config(project_root: Path, config: AiDocConfig, output_root: Path) -> AiDocConfig:
    protected = [f"{DEFAULT_OPTIMIZER_OUTPUT_ROOT}/**"]
    protected.extend(_relative_output_excludes(project_root, output_root))
    excludes = [*config.exclude, *[pattern for pattern in protected if pattern not in config.exclude]]
    return config.model_copy(update={"exclude": excludes})


def discover_optimization_sources(
    project_root: Path,
    config: AiDocConfig,
    token_counter: TokenCounter,
    output_root: Path,
) -> DocumentationSnapshot:
    return discover_markdown(project_root, optimization_source_config(project_root, config, output_root), token_counter)


def run_optimization_static_check(
    project_root: Path,
    config: AiDocConfig,
    extensions: ExtensionRegistry,
    token_counter: TokenCounter,
    output_root: Path,
) -> CheckReport:
    return run_static_check(
        project_root,
        optimization_source_config(project_root, config, output_root),
        extensions=extensions,
        token_counter=token_counter,
    )


def _relative_output_excludes(project_root: Path, output_root: Path) -> list[str]:
    try:
        relative = output_root.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return []
    if relative in {"", "."}:
        return []
    pattern = f"{relative.rstrip('/')}/**"
    return [] if pattern == f"{DEFAULT_OPTIMIZER_OUTPUT_ROOT}/**" else [pattern]
