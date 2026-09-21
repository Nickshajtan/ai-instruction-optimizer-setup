from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_observability_disabled_does_not_create_observation_file(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0
    assert not (tmp_path / ".ai-doc" / "observations.jsonl").exists()
    assert "Observability is disabled for this run" not in result.stderr


def test_explicit_config_omitting_observability_warns_without_writing_observations(tmp_path: Path) -> None:
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--config", str(config), "--format", "json"])

    assert result.exit_code == 0
    assert "Observability is disabled for this run" in result.stderr
    assert str(config) in result.stderr
    assert not (tmp_path / ".ai-doc" / "observations.jsonl").exists()


def test_explicit_config_disabling_observability_warns(tmp_path: Path) -> None:
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
observability:
  enabled: false
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--config", str(config), "--format", "json"])

    assert result.exit_code == 0
    assert result.stderr.count("Observability is disabled for this run") == 1
    assert not (tmp_path / ".ai-doc" / "observations.jsonl").exists()


def test_explicit_config_enabling_observability_does_not_warn(tmp_path: Path) -> None:
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include: [AGENTS.md]
profiles:
  AGENTS.md: instruction
observability:
  enabled: true
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nRun validation.\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["check", str(tmp_path), "--config", str(config), "--format", "json"])

    assert result.exit_code == 0
    assert "Observability is disabled for this run" not in result.stderr
    assert (tmp_path / ".ai-doc" / "observations.jsonl").exists()


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


def test_optimize_observation_records_pairwise_execution_facts(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
observability:
  enabled: true
components:
  provider: company
optimization:
  strategy: balanced
  pairwise_semantic: true
  population:
    initial_candidates: 2
  search:
    max_candidates: 2
    max_llm_requests: 20
extensions:
  - path: .ai-doc/extensions/observed.py
""",
    )
    _write_provider_extension(tmp_path)

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--format", "json"])

    assert result.exit_code in {0, 4}
    record = json.loads((tmp_path / ".ai-doc" / "observations.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    pairwise = record["optimization"]["pairwise"]
    assert pairwise["requested"] is True
    assert pairwise["comparisons_performed"] >= 1
    assert pairwise["uncertain"] >= 1


def test_pairwise_semantic_warns_when_requested_but_not_performed(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "conservative", "--pairwise-semantic", "--format", "json"],
    )

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["run"]["pairwise_semantic_requested"] is True
    assert report["run"]["pairwise_comparisons_performed"] == 0
    assert "Pairwise semantic judging was requested but not performed:" in result.stderr
    assert "This run did NOT receive a pairwise semantic judgment." in result.stderr


def test_require_pairwise_semantic_fails_when_not_performed(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--strategy", "conservative", "--require-pairwise-semantic", "--format", "json"],
    )

    assert result.exit_code == 3
    report = json.loads(result.stdout)
    assert report["run"]["pairwise_semantic_requested"] is True
    assert report["run"]["pairwise_comparisons_performed"] == 0
    assert "Required pairwise semantic judging was not performed:" in result.stderr


def test_require_pairwise_semantic_succeeds_when_comparison_occurs(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
components:
  provider: company
optimization:
  strategy: balanced
  population:
    initial_candidates: 2
  search:
    max_candidates: 2
    max_llm_requests: 20
extensions:
  - path: .ai-doc/extensions/observed.py
""",
    )
    _write_provider_extension(tmp_path)

    result = CliRunner().invoke(app, ["optimize", str(tmp_path), "--require-pairwise-semantic", "--format", "json"])

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["run"]["pairwise_semantic_requested"] is True
    assert report["run"]["pairwise_comparisons_performed"] >= 1
    assert "not performed" not in result.stderr


def test_optimize_explicit_config_cannot_rediscover_default_output_root(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "source.md").write_text("# Source\n\nRun validation.\n", encoding="utf-8")
    generated = tmp_path / ".ai-doc-output" / "previous" / "candidates" / "C001"
    generated.mkdir(parents=True)
    (generated / "generated.md").write_text("# Generated\n\nThis is optimizer output.\n", encoding="utf-8")
    nested = tmp_path / ".ai-doc-output" / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "candidate.md").write_text("# Nested Generated\n\nIgnore me.\n", encoding="utf-8")
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include:
  - "**/*.md"
exclude:
  - "vendor/**"
profiles:
  "docs/**/*.md": reference
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--config", str(config), "--strategy", "conservative", "--format", "json"],
    )

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["baseline"]["files_analyzed"] == 1
    assert report["baseline"]["profiles"] == {"docs/source.md": "reference"}


def test_optimize_protects_custom_output_root_when_inside_project(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "source.md").write_text("# Source\n\nRun validation.\n", encoding="utf-8")
    generated = tmp_path / "tmp" / "optimizer-results" / "previous"
    generated.mkdir(parents=True)
    (generated / "generated.md").write_text("# Generated\n\nThis is optimizer output.\n", encoding="utf-8")
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include:
  - "**/*.md"
profiles:
  "docs/**/*.md": reference
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "optimize",
            str(tmp_path),
            "--config",
            str(config),
            "--output",
            "tmp/optimizer-results",
            "--strategy",
            "conservative",
            "--format",
            "json",
        ],
    )

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["baseline"]["files_analyzed"] == 1
    assert report["baseline"]["profiles"] == {"docs/source.md": "reference"}


def test_optimize_protects_normalized_custom_output_root(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "source.md").write_text("# Source\n\nRun validation.\n", encoding="utf-8")
    generated = tmp_path / "tmp" / "optimizer-results"
    generated.mkdir(parents=True)
    (generated / "generated.md").write_text("# Generated\n\nThis is optimizer output.\n", encoding="utf-8")
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include:
  - "**/*.md"
profiles:
  "docs/**/*.md": reference
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "optimize",
            str(tmp_path),
            "--config",
            str(config),
            "--output",
            "tmp/../tmp/optimizer-results",
            "--strategy",
            "conservative",
            "--format",
            "json",
        ],
    )

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["baseline"]["files_analyzed"] == 1
    assert report["baseline"]["profiles"] == {"docs/source.md": "reference"}


def test_optimize_does_not_exclude_similarly_named_unrelated_directories(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "source.md").write_text("# Source\n\nRun validation.\n", encoding="utf-8")
    similar = tmp_path / "notes" / ".ai-doc-output-archive"
    similar.mkdir(parents=True)
    (similar / "kept.md").write_text("# Kept\n\nRun archive validation.\n", encoding="utf-8")
    config = tmp_path / "scoped.yaml"
    config.write_text(
        """
version: 1
include:
  - "**/*.md"
profiles:
  "docs/**/*.md": reference
  "notes/**/*.md": reference
""",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["optimize", str(tmp_path), "--config", str(config), "--strategy", "conservative", "--format", "json"],
    )

    assert result.exit_code in {0, 4}
    report = json.loads(result.stdout)
    assert report["baseline"]["profiles"] == {
        "docs/source.md": "reference",
        "notes/.ai-doc-output-archive/kept.md": "reference",
    }


def test_generic_discovery_can_still_inspect_optimizer_output_when_configured(tmp_path: Path) -> None:
    generated = tmp_path / ".ai-doc-output" / "previous"
    generated.mkdir(parents=True)
    (generated / "generated.md").write_text("# Generated\n\nInspectable artifact.\n", encoding="utf-8")
    config = DEFAULT_CONFIG.model_copy(
        update={
            "include": [".ai-doc-output/**/*.md"],
            "exclude": [],
        },
        deep=True,
    )

    snapshot = discover_markdown(tmp_path, config, ApproximateTokenCounter())

    assert [document.relative_path for document in snapshot.documents] == [
        ".ai-doc-output/previous/generated.md"
    ]


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
