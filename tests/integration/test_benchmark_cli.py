from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def test_benchmark_cli_reports_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        """{
  "schema_version": 1,
  "cases": [{
    "id": "task-1",
    "repository": "example/repo",
    "task": "Make a change",
    "runs": [
      {"run_id": "b1", "variant": "baseline", "success": false},
      {"run_id": "b2", "variant": "baseline", "success": false},
      {"run_id": "b3", "variant": "baseline", "success": false},
      {"run_id": "c1", "variant": "candidate", "success": true},
      {"run_id": "c2", "variant": "candidate", "success": true},
      {"run_id": "c3", "variant": "candidate", "success": true}
    ]
  }]
}""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["benchmark", str(evidence)])
    assert result.exit_code == 0
    assert '"improved": 1' in result.stdout
    assert '"task_success_delta"' in result.stdout
