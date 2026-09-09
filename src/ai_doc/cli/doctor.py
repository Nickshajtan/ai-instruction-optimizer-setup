from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ai_doc.diagnostics import Capability, DoctorReport, build_doctor_report
from ai_doc.reporting.json import render_json
from ai_doc.root import discover_project_root


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


def doctor_command(
    path: Annotated[Path, typer.Argument(help="Project path.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    output_format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format.")
    ] = OutputFormat.CONSOLE,
) -> None:
    project_root = discover_project_root(path, root)
    report = build_doctor_report(project_root)
    typer.echo(render_json(report) if output_format == OutputFormat.JSON else _render_console(report))


def _render_console(report: DoctorReport) -> str:
    lines = [
        "AI Documentation Optimizer",
        "",
        f"Version: {report.version}",
        f"Project root: {report.project_root}",
        f"Runtime mode: {report.runtime_mode}",
        "",
        "Core",
    ]
    lines.extend(_capability_lines(report.core))
    lines.append("")
    lines.append("Runtime")
    lines.extend(_capability_lines(report.runtime))
    lines.append("")
    lines.append("Optional integrations")
    lines.extend(_capability_lines(report.optional_integrations))
    lines.append("")
    lines.append("LLM providers")
    lines.extend(_capability_lines(report.llm_providers))
    return "\n".join(lines) + "\n"


def _capability_lines(items: list[Capability]) -> list[str]:
    lines: list[str] = []
    for item in items:
        detail = f" ({item.detail})" if item.detail else ""
        lines.append(f"  {item.status.upper()} {item.name}{detail}")
    return lines
