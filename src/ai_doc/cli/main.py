from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ai_doc import __version__
from ai_doc.cli.benchmark import benchmark_command
from ai_doc.cli.check import check_command
from ai_doc.cli.doctor import doctor_command
from ai_doc.cli.optimize import optimize_command
from ai_doc.cli.setup import setup_command
from ai_doc.config.loader import ConfigError, write_default_config


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


app = typer.Typer(help="Analyze and optimize AI-facing Markdown documentation.")


@app.callback()
def main(
    _version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, help="Show version and exit."),
    ] = None,
) -> None:
    pass


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="Repository root.")] = Path("."),
) -> None:
    """Create starter configuration and eval directory without overwriting files."""
    root = path.resolve()
    try:
        written = write_default_config(root)
    except OSError as exc:
        raise typer.Exit(1) from exc
    if written:
        for item in written:
            typer.echo(f"created {item.relative_to(root)}")
    else:
        typer.echo("ai-doc configuration already exists")


app.command(name="check")(check_command)
app.command(name="optimize")(optimize_command)
app.command(name="benchmark")(benchmark_command)
app.command(name="doctor")(doctor_command)
app.command(name="setup")(setup_command)


@app.command()
def version() -> None:
    """Show ai-doc version."""
    typer.echo(__version__)


def config_error(exc: ConfigError) -> None:
    typer.echo(str(exc), err=True)
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
