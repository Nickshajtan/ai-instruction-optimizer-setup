from __future__ import annotations

import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from ai_doc.cli.main import app


def _write_project(root: Path, config_extra: str = "") -> None:
    (root / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: [AGENTS.md, 'docs/**/*.md']
profiles:
  AGENTS.md: instruction
  'docs/**': reference
optimization:
  strategy: balanced
  population:
    initial_candidates: 2
  search:
    max_candidates: 2
    max_llm_requests: 20
    max_cost_usd: 2.00
{config_extra}
""",
        encoding="utf-8",
    )
    (root / "docs").mkdir(exist_ok=True)
    (root / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST run validation.\n"
        "- Prefer module-local instructions when they exist.\n"
        "- Prefer module-local instructions when they exist.\n"
        "- Use best practices for changes.\n",
        encoding="utf-8",
    )
    (root / "docs" / "guide.md").write_text("# Guide\n\nUse the guide.\n", encoding="utf-8")


def _extension(root: Path, text: str) -> None:
    extension_dir = root / ".ai-doc" / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    (extension_dir / "contracts.py").write_text(text, encoding="utf-8")


def _run_json(args: list[str]) -> dict[str, object]:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.output[result.output.index("{") :])


def test_l3_python_token_counter_affects_static_report(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
components:
  token_counter: company
extensions:
  - path: .ai-doc/extensions/contracts.py
""",
    )
    _extension(
        tmp_path,
        """
class CompanyCounter:
    label = "company"
    def count(self, text, model=None):
        return 7 if text.strip() else 0
    def count_many(self, texts, model=None):
        return [self.count(text, model) for text in texts]

def register(registry):
    registry.add_token_counter("company", CompanyCounter())
""",
    )

    report = _run_json(["check", str(tmp_path), "--format", "json"])

    assert report["token_counter"] == "company"
    assert report["total_tokens"] == 14


def test_l3_python_evaluator_affects_deep_check(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
evaluation:
  deep:
    evaluator: company
extensions:
  - path: .ai-doc/extensions/contracts.py
""",
    )
    _extension(
        tmp_path,
        """
from ai_doc.api.v1 import EvaluationResult

class CompanyEvaluator:
    def evaluate(self, baseline, candidate, suite):
        return EvaluationResult(engine="company-python", passed=True)

def register(registry):
    registry.add_evaluator("company", CompanyEvaluator())
""",
    )

    report = _run_json(["check", str(tmp_path), "--deep", "--format", "json"])

    assert report["evaluation"]["engine"] == "company-python"


def test_l3_python_recommendation_policy_affects_optimize(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
components:
  recommendation_policy: company
extensions:
  - path: .ai-doc/extensions/contracts.py
""",
    )
    _extension(
        tmp_path,
        """
class CompanyPolicy:
    def choose(self, baseline, frontier):
        for candidate in frontier:
            if candidate.id != baseline.id:
                candidate.evidence.recommendation_reason = "company selected"
                return candidate
        return None

def register(registry):
    registry.add_recommendation_policy("company", CompanyPolicy())
""",
    )

    report = _run_json(["optimize", str(tmp_path), "--format", "json"])

    assert report["run"]["recommended_candidate_id"] is not None
    assert "company selected" in json.dumps(report)


def test_l3_python_provider_affects_semantic_generation_and_budgeting(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        """
components:
  provider: company
extensions:
  - path: .ai-doc/extensions/contracts.py
""",
    )
    _extension(
        tmp_path,
        """
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
                usage=ProviderUsage(input_tokens=5, output_tokens=6)
            )
        return SemanticResponse(data={}, usage=ProviderUsage(input_tokens=1))

def register(registry):
    registry.add_provider("company", CompanyProvider())
""",
    )

    report = _run_json(["optimize", str(tmp_path), "--format", "json"])

    assert "provider generated" in json.dumps(report)
    assert report["run"]["total_cost"]["generation_requests"] >= 1
    assert report["run"]["total_cost"]["generation_input_tokens"] >= 5


def _process_script(root: Path) -> Path:
    script = root / "process_extension.py"
    script.write_text(
        """
from __future__ import annotations
import json
import sys

request = json.loads(sys.stdin.read())
op = request["operation"]
payload = request["payload"]
result = {}
if op == "analyze":
    result = {"findings": [{
        "code": "PROCESS_ANALYZER",
        "category": "risk",
        "severity": "info",
        "path": "AGENTS.md",
        "section": None,
        "message": "process analyzer ran",
        "evidence": {},
        "suggestion": None
    }]}
elif op == "count_tokens":
    result = {"counts": {item["id"]: 11 for item in payload["items"]}}
elif op == "evaluate":
    result = {"engine": "process-evaluator", "passed": True, "cases": []}
elif op == "recommend":
    selected = next((item["id"] for item in payload["candidates"] if item["id"] != payload["baseline_id"]), None)
    result = {"candidate_id": selected, "reason": "process selected"}
elif op == "complete":
    requested = payload["operation"]
    inner = payload["payload"]
    if requested == "discover_invariants":
        result = {"data": {"invariants": []}, "usage": {"requests": 1, "input_tokens": 2}}
    elif requested == "verify_invariant":
        result = {"data": {"status": "preserved"}, "usage": {"requests": 1, "input_tokens": 2}}
    elif requested == "generate_candidate":
        docs = dict(inner["documents"])
        docs["AGENTS.md"] += "\\nProcess provider generated.\\n"
        result = {
            "data": {
                "proposal": {"operations": [{
                    "type": "rewrite",
                    "target": "AGENTS.md",
                    "reason": "process provider generated",
                    "expected_clarity_effect": "clearer",
                    "expected_finops_effect": "neutral",
                    "risk": "low",
                    "objective": ["clarity"]
                }]},
                "documents": docs
            },
            "usage": {"requests": 1, "input_tokens": 5, "output_tokens": 6}
        }
    else:
        result = {"data": {}, "usage": {"requests": 1}}
response = {
    "protocol": request["protocol"],
    "request_id": request["request_id"],
    "status": "ok",
    "result": result,
}
print(json.dumps(response))
""",
        encoding="utf-8",
    )
    return script


def _command_yaml(script: Path) -> str:
    return f'["{sys.executable.replace(chr(92), "/")}", "{script.as_posix()}"]'


def test_l4_process_analyzer_and_token_counter_affect_check(tmp_path: Path) -> None:
    script = _process_script(tmp_path)
    _write_project(
        tmp_path,
        f"""
components:
  token_counter: process-counter
extension_runtime:
  analyzers:
    process-analyzer:
      command: {_command_yaml(script)}
  token_counters:
    process-counter:
      command: {_command_yaml(script)}
""",
    )

    report = _run_json(["check", str(tmp_path), "--format", "json"])

    assert report["token_counter"] == "process-counter"
    assert report["total_tokens"] == 22
    assert "PROCESS_ANALYZER" in json.dumps(report)


def test_l4_process_evaluator_affects_deep_check(tmp_path: Path) -> None:
    script = _process_script(tmp_path)
    _write_project(
        tmp_path,
        f"""
evaluation:
  deep:
    evaluator: process-evaluator
extension_runtime:
  evaluators:
    process-evaluator:
      command: {_command_yaml(script)}
""",
    )

    report = _run_json(["check", str(tmp_path), "--deep", "--format", "json"])

    assert report["evaluation"]["engine"] == "process-evaluator"


def test_l4_process_recommendation_policy_affects_optimize(tmp_path: Path) -> None:
    script = _process_script(tmp_path)
    _write_project(
        tmp_path,
        f"""
components:
  recommendation_policy: process-policy
extension_runtime:
  recommendation_policies:
    process-policy:
      command: {_command_yaml(script)}
""",
    )

    report = _run_json(["optimize", str(tmp_path), "--format", "json"])

    assert report["run"]["recommended_candidate_id"] is not None
    assert "process selected" in json.dumps(report)


def test_l4_process_provider_affects_semantic_generation(tmp_path: Path) -> None:
    script = _process_script(tmp_path)
    _write_project(
        tmp_path,
        f"""
components:
  provider: process-provider
extension_runtime:
  providers:
    process-provider:
      command: {_command_yaml(script)}
""",
    )

    report = _run_json(["optimize", str(tmp_path), "--format", "json"])

    assert "process provider generated" in json.dumps(report)
    assert report["run"]["total_cost"]["generation_requests"] >= 1
