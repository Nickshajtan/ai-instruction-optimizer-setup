from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def _write_evidence(path: Path, *, baseline_success: bool, candidate_success: bool) -> None:
    path.write_text(
        f"""{{
  "schema_version": 1,
  "cases": [{{
    "id": "task-1",
    "repository": "example/repo",
    "task": "Make a change",
    "runs": [
      {{"run_id": "b1", "variant": "baseline", "success": {str(baseline_success).lower()}}},
      {{"run_id": "b2", "variant": "baseline", "success": {str(baseline_success).lower()}}},
      {{"run_id": "b3", "variant": "baseline", "success": {str(baseline_success).lower()}}},
      {{"run_id": "c1", "variant": "candidate", "success": {str(candidate_success).lower()}}},
      {{"run_id": "c2", "variant": "candidate", "success": {str(candidate_success).lower()}}},
      {{"run_id": "c3", "variant": "candidate", "success": {str(candidate_success).lower()}}}
    ]
  }}]
}}""",
        encoding="utf-8",
    )


def test_benchmark_cli_reports_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    _write_evidence(evidence, baseline_success=False, candidate_success=True)
    result = CliRunner().invoke(app, ["benchmark", str(evidence)])
    assert result.exit_code == 0
    assert '"improved": 1' in result.stdout
    assert '"task_success_delta"' in result.stdout
    assert '"input_tokens_delta"' in result.stdout


def test_benchmark_cli_can_fail_on_meaningful_regression(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    _write_evidence(evidence, baseline_success=True, candidate_success=False)
    result = CliRunner().invoke(app, ["benchmark", str(evidence), "--fail-on-regression"])
    assert result.exit_code == 5
    assert '"regressed": 1' in result.stdout
