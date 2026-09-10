from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def _write_fixture(root: Path) -> None:
    (root / ".ai-doc.yaml").write_text(
        """
version: 1
include: [AGENTS.md, 'docs/**/*.md']
profiles:
  AGENTS.md: instruction
  'docs/**': reference
optimization:
  strategy: search
  search:
    generations: 3
    initial_candidates: 4
    children_per_generation: 2
    max_candidates: 5
    max_llm_requests: 10
    max_cost_usd: 1.00
    patience: 2
""",
        encoding="utf-8",
    )
    (root / "docs").mkdir()
    (root / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST run relevant validation before completion.\n"
        "- NEVER modify generated files.\n"
        "- Prefer module-local instructions when they exist.\n"
        "- Prefer module-local instructions when they exist.\n"
        "- Use best practices for changes.\n\n"
        "## Testing Examples\n\n"
        + "Example A: run the narrow test, then broaden validation.\n" * 40,
        encoding="utf-8",
    )
    (root / "docs" / "testing.md").write_text("# Testing\n\nRun narrow tests first.\n", encoding="utf-8")


def test_balanced_generates_competing_frontier_and_lineage(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "balanced", "--show-frontier"],
    )
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    assert (run_dir / "frontier.json").exists()
    assert (run_dir / "lineage.json").exists()
    assert len(list((run_dir / "candidates").iterdir())) > 1


def test_search_stops_on_candidate_budget(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "search", "--max-candidates", "2"],
    )
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    assert "stopped_candidate_budget" in (run_dir / "run.json").read_text(encoding="utf-8")


def test_request_budget_preserves_existing_results(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "search", "--max-requests", "1"],
    )
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    assert (run_dir / "run.json").exists()
    assert "stopped_request_budget" in (run_dir / "run.json").read_text(encoding="utf-8")
