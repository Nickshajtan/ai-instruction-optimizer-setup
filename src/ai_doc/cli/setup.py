from __future__ import annotations

from typing import Annotated

import typer

from ai_doc.optional_dependencies import OptionalDependencyError, install_deep_dependencies


def setup_command(
    deep: Annotated[
        bool, typer.Option("--deep", help="Install optional deep-evaluation dependencies.")
    ] = False,
) -> None:
    if not deep:
        typer.echo("Nothing to set up. Use --deep to install optional deep-evaluation dependencies.")
        return
    try:
        installed = install_deep_dependencies()
    except OptionalDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo("Installed optional dependencies:")
    for requirement in installed:
        typer.echo(f"  {requirement}")
