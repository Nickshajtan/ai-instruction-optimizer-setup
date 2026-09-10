import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def _fixture_command() -> str:
    fixture = Path(__file__).parents[1] / "fixtures" / "fake_semantic_provider.py"
    return f'"{sys.executable}" "{fixture}"'


def _write_project(root: Path, *, max_input_tokens: int) -> None:
    (root / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
optimization:
  strategy: balanced
  population:
    initial_candidates: 2
  search:
    generations: 1
    initial_candidates: 2
    children_per_generation: 0
    max_candidates: 2
    max_llm_requests: 20
    max_input_tokens: {max_input_tokens}
    max_output_tokens: 1000
    max_cost_usd: 1.00
    patience: 0
""",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text(
        "# Rules\n\n"
        "Validate migrations before completion.\n\n"
        "Use best practices for migration changes.\n",
        encoding="utf-8",
    )
    eval_dir = root / ".ai-doc" / "evals"
    eval_dir.mkdir(parents=True)
    (eval_dir / "migration.yaml").write_text(
        """
id: migration
profile: coding-task
task: Validate a migration change.
expected:
  required:
    - validate the migration before completion
""",
        encoding="utf-8",
    )


def _run_json(root: Path) -> dict[str, object]:
    run_dir = next((root / ".ai-doc-output").iterdir())
    return json.loads((run_dir / "run.json").read_text(encoding="utf-8"))


def _serialized_input_tokens(total_cost: dict[str, object]) -> int:
    return sum(
        int(total_cost[key])
        for key in (
            "generation_input_tokens",
            "evaluation_input_tokens",
            "prompt_suboptimizer_input_tokens",
        )
    )


def _serialized_requests(total_cost: dict[str, object]) -> int:
    return sum(
        int(total_cost[key])
        for key in (
            "generation_requests",
            "evaluation_requests",
            "prompt_suboptimizer_requests",
        )
    )


def test_cli_uses_production_semantic_command_and_writes_real_usage(tmp_path: Path, monkeypatch) -> None:
    _write_project(tmp_path, max_input_tokens=10_000)
    monkeypatch.setenv("AI_DOC_SEMANTIC_COMMAND", _fixture_command())
    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "balanced", "--deep", "--non-interactive"],
    )
    assert result.exit_code in {0, 4}
    run = _run_json(tmp_path)
    total_cost = run["total_cost"]
    assert isinstance(total_cost, dict)
    assert int(total_cost["generation_requests"]) >= 1
    assert int(total_cost["evaluation_requests"]) >= 1
    assert _serialized_input_tokens(total_cost) > 0
    assert (tmp_path / ".ai-doc-output").exists()


def test_cli_persists_discovery_overrun_as_normal_budget_stop(tmp_path: Path, monkeypatch) -> None:
    _write_project(tmp_path, max_input_tokens=50)
    monkeypatch.setenv("AI_DOC_SEMANTIC_COMMAND", _fixture_command())
    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "balanced", "--deep", "--non-interactive"],
    )
    assert result.exit_code == 4
    run = _run_json(tmp_path)
    assert run["stopped_reason"] == "stopped_token_budget"
    metadata = run["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["budget_stop_stage"] == "semantic invariant discovery"
    total_cost = run["total_cost"]
    assert isinstance(total_cost, dict)
    assert _serialized_input_tokens(total_cost) == 100
    assert _serialized_requests(total_cost) == 1
    assert (next((tmp_path / ".ai-doc-output").iterdir()) / "report.json").exists()
