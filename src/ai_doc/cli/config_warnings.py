from __future__ import annotations

from pathlib import Path

import typer

from ai_doc.config.models import AiDocConfig


def warn_if_explicit_config_disables_observability(config_path: Path | None, config: AiDocConfig) -> None:
    if config_path is None or config.observability.enabled:
        return
    typer.echo(
        f"Observability is disabled for this run; no observations will be written (config: {config_path}).",
        err=True,
    )
