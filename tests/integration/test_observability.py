from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def test_observability_disabled_does_not_create_observation_file(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    assert not (tmp_path / ".ai-doc" / "observations.jsonl").exists()


def test_enabled_observability_appends_parseable_privacy_safe_records(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
observability:
  enabled: true
extensions:
  - path: .ai-doc/extensions/observed.py
""",
    )
    _write_extension(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\nSECRET DOCUMENT BODY should not appear in observations.\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    first = runner.invoke(app, ["check", str(tmp_path), "--format", "json"])
    second = runner.invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    log_path = tmp_path / ".ai-doc" / "observations.jsonl"
    raw_lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 2
    records = [json.loads(line) for line in raw_lines]
    assert {record["schema"] for record in records} == {"ai-doc.observation/v1"}
    assert records[0]["run_id"] != records[1]["run_id"]
    assert records[0]["command"] == "check"
    assert records[0]["status"] == "completed"
    assert records[0]["context"]["document_count"] == 1
    assert records[0]["tiers"][0]["tier"] == "a0"
    assert records[0]["tiers"][0]["status"] == "completed"
    assert records[0]["findings"][0]["rule"] == "OBSERVED_FINDING"
    assert records[0]["findings"][0]["fingerprint"] == records[1]["findings"][0]["fingerprint"]
    assert "AGENTS.md" not in raw_lines[0]
    assert "SECRET DOCUMENT BODY" not in raw_lines[0]


def test_observation_write_failure_preserves_primary_check_result(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
observability:
  enabled: true
  path: .
""",
    )

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    assert '"files_analyzed": 1' in result.output
    assert "Observation logging failed:" in result.output
    assert "Traceback" not in result.output


def test_optimize_observation_records_provider_usage_when_available(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
observability:
  enabled: true
components:
  provider: company
optimization:
  strategy: balanced
  population:
    initial_candidates: 2
  search:
    max_candidates: 2
    max_llm_requests: 20
    max_cost_usd: 2.00
extensions:
  - path: .ai-doc/extensions/observed.py
""",
    )
    _write_provider_extension(tmp_path)

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--format", "json"])

    assert result.exit_code in {0, 4}
    records = [
        json.loads(line)
        for line in (tmp_path / ".ai-doc" / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    record = records[-1]
    assert record["command"] == "optimize"
    assert record["providers"]
    operation_records = [item for item in record["providers"] if item["operation"] != "aggregate"]
    aggregate_records = [item for item in record["providers"] if item["operation"] == "aggregate"]
    assert len(operation_records) >= 2
    assert len(aggregate_records) == 1
    assert all(item["token_semantics"] == "reported" for item in record["providers"])
    assert all(item["input_tokens"] > 0 for item in operation_records)
    assert all(item["cost_usd"] is None for item in operation_records)
    assert all(item["cache_hits"] is None for item in operation_records)
    assert aggregate_records[0]["cost_usd"] == "0.01"
    assert aggregate_records[0]["cost_source"] == "provider"
    assert sum(1 for item in record["providers"] if item["cost_usd"] is not None) == 1
    assert "provider" not in record["providers"][0]
    assert "model" not in record["providers"][0]
    assert record["optimization"]["candidates_generated"] >= 1


def _write_project(root: Path, config_extra: str = "") -> None:
    (root / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
{config_extra}
""",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")


def _write_extension(root: Path) -> None:
    extension_dir = root / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (extension_dir / "observed.py").write_text(
        """
from ai_doc.api.v1 import Finding


class ObservedAnalyzer:
    def analyze(self, context):
        return [
            Finding(
                code="OBSERVED_FINDING",
                category="risk",
                severity="info",
                path="AGENTS.md",
                section=None,
                message="observed structured finding",
                evidence={},
                suggestion=None,
            )
        ]


def register(registry):
    registry.add_analyzer(ObservedAnalyzer())
""",
        encoding="utf-8",
    )


def _write_provider_extension(root: Path) -> None:
    extension_dir = root / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True)
    (extension_dir / "observed.py").write_text(
        """
from decimal import Decimal

from ai_doc.api.v1 import ProviderUsage, SemanticResponse


class CompanyProvider:
    def invoke(self, operation, payload):
        if operation == "discover_invariants":
            return SemanticResponse(data={"invariants": []}, usage=ProviderUsage(input_tokens=3))
        if operation == "verify_invariant":
            return SemanticResponse(data={"status": "preserved"}, usage=ProviderUsage(input_tokens=4))
        if operation == "generate_candidate":
            docs = dict(payload["documents"])
            docs["AGENTS.md"] += "\\nProvider generated.\\n"
            return SemanticResponse(
                data={
                    "proposal": {
                        "operations": [{
                            "type": "rewrite",
                            "target": "AGENTS.md",
                            "reason": "provider generated",
                            "expected_clarity_effect": "clearer",
                            "expected_finops_effect": "neutral",
                            "risk": "low",
                            "objective": ["clarity"]
                        }]
                    },
                    "documents": docs
                },
                usage=ProviderUsage(input_tokens=5, output_tokens=6, cost_usd=Decimal("0.01")),
            )
        return SemanticResponse(data={}, usage=ProviderUsage(input_tokens=1))


def register(registry):
    registry.add_provider("company", CompanyProvider())
""",
        encoding="utf-8",
    )
