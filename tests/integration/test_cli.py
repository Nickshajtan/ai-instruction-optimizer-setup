from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def test_cli_check_and_optimize(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        "version: 1\ninclude: [AGENTS.md, 'docs/**/*.md']\nprofiles: {AGENTS.md: instruction, 'docs/**': reference}\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST run validation.\n"
        "- NEVER modify generated files.\n"
        "- Repeat routing rule.\n"
        "- Repeat routing rule.\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["check", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["optimize", str(tmp_path), "--output", ".ai-doc-output"])
    assert result.exit_code == 0
    outputs = list((tmp_path / ".ai-doc-output").glob("*/report.json"))
    assert outputs
