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
        "## Testing Examples\n\n" + "Example A: run the narrow test, then broaden validation.\n" * 40,
        encoding="utf-8",
    )
    (root / "docs" / "testing.md").write_text("# Testing\n\nRun narrow tests first.\n", encoding="utf-8")


def test_balanced_generates_competing_frontier_and_lineage(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["optimize", str(tmp_path), "--strategy", "balanced", "--show-frontier"])
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    assert (run_dir / "frontier.json").exists()
    assert (run_dir / "lineage.json").exists()
    assert len(list((run_dir / "candidates").iterdir())) > 1


def test_search_stops_on_candidate_budget(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["optimize", str(tmp_path), "--strategy", "search", "--max-candidates", "2"])
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    assert "stopped_candidate_budget" in (run_dir / "run.json").read_text(encoding="utf-8")


def test_deterministic_search_does_not_consume_llm_request_budget(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app, ["optimize", str(tmp_path), "--strategy", "search", "--max-requests", "0", "--max-candidates", "2"]
    )
    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    run_json = (run_dir / "run.json").read_text(encoding="utf-8")
    assert "stopped_request_budget" not in run_json
    assert '"generation_requests": 0' in run_json
    assert '"evaluation_requests": 0' in run_json


def test_gepa_disabled_does_not_require_models(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--strategy", "balanced", "--max-candidates", "1"])

    assert result.exit_code == 0


def test_gepa_requires_reflection_model(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _append_gepa_config(tmp_path, "mutation_model: explicit-mutation\n")

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--gepa"])

    assert result.exit_code == 1
    assert "optimization.gepa.reflection_model" in result.output


def test_gepa_requires_mutation_model(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _append_gepa_config(tmp_path, "reflection_model: explicit-reflection\n")

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--gepa"])

    assert result.exit_code == 1
    assert "optimization.gepa.mutation_model" in result.output


def test_gepa_requires_models_even_with_ambient_openai_key(monkeypatch, tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-test-key")

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--gepa"])

    assert result.exit_code == 1
    assert "optimization.gepa.reflection_model" in result.output
    assert "optimization.gepa.mutation_model" in result.output


def test_gepa_with_explicit_models_keeps_existing_path_available(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    _append_gepa_config(
        tmp_path,
        "reflection_model: explicit-reflection\n    mutation_model: explicit-mutation\n",
    )

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--gepa", "--max-candidates", "1"])

    assert result.exit_code == 0
    run_dir = next((tmp_path / ".ai-doc-output").iterdir())
    run_json = (run_dir / "run.json").read_text(encoding="utf-8")
    assert '"reflection_model": "explicit-reflection"' in run_json
    assert '"mutation_model": "explicit-mutation"' in run_json


def _append_gepa_config(root: Path, body: str) -> None:
    with (root / ".ai-doc.yaml").open("a", encoding="utf-8") as handle:
        handle.write(f"\n  gepa:\n    {body}")
