from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
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
    result = CliRunner().invoke(app, _with_allow_extensions(args))
    assert result.exit_code == 0, result.output
    return json.loads(result.output[result.output.index("{") :])


def _run_json_with_exit(args: list[str], exit_code: int) -> dict[str, object]:
    result = CliRunner().invoke(app, _with_allow_extensions(args))
    assert result.exit_code == exit_code, result.output
    return json.loads(result.output[result.output.index("{") :])


def _with_allow_extensions(args: list[str]) -> list[str]:
    command = args[0] if args else ""
    if command in {"check", "optimize", "probe", "execute"} and "--allow-extensions" not in args:
        return [*args, "--allow-extensions"]
    return args


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


def test_l3_python_provider_usage_stops_at_core_request_budget(tmp_path: Path) -> None:
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
        return SemanticResponse(data={"invariants": []}, usage=ProviderUsage(requests=1, input_tokens=3))

def register(registry):
    registry.add_provider("company", CompanyProvider())
""",
    )

    report = _run_json_with_exit(["optimize", str(tmp_path), "--format", "json", "--max-requests", "1"], 4)

    assert report["run"]["stopped_reason"] == "stopped_request_budget"
    assert report["run"]["total_cost"]["evaluation_requests"] == 1


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
    result = {"payload_version": 1, "findings": [{
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
    result = {"payload_version": 1, "counts": {item["id"]: 11 for item in payload["items"]}}
elif op == "evaluate":
    result = {"payload_version": 1, "engine": "process-evaluator", "passed": True, "cases": []}
elif op == "recommend":
    selected = next((item["id"] for item in payload["candidates"] if item["id"] != payload["baseline_id"]), None)
    result = {"payload_version": 1, "candidate_id": selected, "reason": "process selected"}
elif op == "complete":
    requested = payload["operation"]
    inner = payload["payload"]
    if requested == "discover_invariants":
        result = {"payload_version": 1, "data": {"invariants": []}, "usage": {"requests": 1, "input_tokens": 2}}
    elif requested == "verify_invariant":
        result = {"payload_version": 1, "data": {"status": "preserved"}, "usage": {"requests": 1, "input_tokens": 2}}
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
            "usage": {"requests": 1, "input_tokens": 5, "output_tokens": 6},
            "payload_version": 1
        }
    else:
        result = {"payload_version": 1, "data": {}, "usage": {"requests": 1}}
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


def _command_yaml_with_args(script: Path, *args: Path) -> str:
    parts = [sys.executable.replace(chr(92), "/"), script.as_posix(), *(arg.as_posix() for arg in args)]
    return "[" + ", ".join(json.dumps(part) for part in parts) + "]"


def _failing_process_counter(root: Path) -> Path:
    script = root / "failing_counter.py"
    script.write_text(
        """
from __future__ import annotations
import json
import sys

request = json.loads(sys.stdin.read())
print(json.dumps({
    "protocol": request["protocol"],
    "request_id": request["request_id"],
    "status": "error",
    "error": {"code": "counter_unavailable", "message": "counter offline"},
}))
""",
        encoding="utf-8",
    )
    return script


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


@pytest.mark.parametrize(
    "command",
    [
        ["check"],
        ["optimize"],
        ["probe"],
        ["execute"],
    ],
)
def test_process_extension_failures_report_clean_cli_errors(tmp_path: Path, command: list[str]) -> None:
    script = _failing_process_counter(tmp_path)
    _write_project(
        tmp_path,
        f"""
components:
  token_counter: failing-counter
extension_runtime:
  token_counters:
    failing-counter:
      command: {_command_yaml(script)}
""",
    )

    result = CliRunner().invoke(app, [*command, str(tmp_path), "--allow-extensions"])

    assert result.exit_code == 1
    assert "counter_unavailable" in result.output
    assert "counter offline" in result.output
    assert "Traceback" not in result.output


def test_analyzers_are_additive_across_python_and_process_extensions(tmp_path: Path) -> None:
    process_script = tmp_path / "named_analyzer.py"
    process_script.write_text(
        """
from __future__ import annotations
import json
import sys

code = sys.argv[1]
request = json.loads(sys.stdin.read())
result = {"payload_version": 1, "findings": [{
    "code": code,
    "category": "risk",
    "severity": "info",
    "path": "AGENTS.md",
    "section": None,
    "message": f"{code} ran",
    "evidence": {},
    "suggestion": None
}]}
print(json.dumps({
    "protocol": request["protocol"],
    "request_id": request["request_id"],
    "status": "ok",
    "result": result,
}))
""",
        encoding="utf-8",
    )
    _write_project(
        tmp_path,
        f"""
extensions:
  - path: .ai-doc/extensions/contracts.py
extension_runtime:
  analyzers:
    process-alpha:
      command: {_command_yaml_with_args(process_script, Path("PROCESS_ALPHA"))}
    process-beta:
      command: {_command_yaml_with_args(process_script, Path("PROCESS_BETA"))}
""",
    )
    _extension(
        tmp_path,
        """
from ai_doc.api.v1 import Finding

class PythonAnalyzer:
    def analyze(self, context):
        return [Finding(
            code="PYTHON_ANALYZER",
            category="risk",
            severity="info",
            path="AGENTS.md",
            section=None,
            message="python analyzer ran",
            evidence={},
            suggestion=None,
        )]

def register(registry):
    registry.add_analyzer(PythonAnalyzer())
""",
    )

    report = _run_json(["check", str(tmp_path), "--format", "json"])

    codes = [finding["code"] for finding in report["findings"]]
    assert "PYTHON_ANALYZER" in codes
    assert "PROCESS_ALPHA" in codes
    assert "PROCESS_BETA" in codes


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


def test_l4_process_provider_usage_stops_at_core_request_budget(tmp_path: Path) -> None:
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

    report = _run_json_with_exit(["optimize", str(tmp_path), "--format", "json", "--max-requests", "1"], 4)

    assert report["run"]["stopped_reason"] == "stopped_request_budget"
    assert report["run"]["total_cost"]["evaluation_requests"] == 1


def test_l4_process_token_counter_batches_repository_discovery(tmp_path: Path) -> None:
    calls_path = tmp_path / "token_counter_calls.txt"
    script = tmp_path / "batching_counter.py"
    script.write_text(
        """
from __future__ import annotations
import json
import sys
from pathlib import Path

calls = Path(sys.argv[1])
current = int(calls.read_text(encoding="utf-8")) if calls.exists() else 0
calls.write_text(str(current + 1), encoding="utf-8")
request = json.loads(sys.stdin.read())
payload = request["payload"]
result = {"payload_version": 1, "counts": {item["id"]: 1 for item in payload["items"]}}
print(json.dumps({
    "protocol": request["protocol"],
    "request_id": request["request_id"],
    "status": "ok",
    "result": result,
}))
""",
        encoding="utf-8",
    )
    (tmp_path / ".ai-doc.yaml").write_text(
        f"""
version: 1
include: ['docs/**/*.md']
profiles:
  'docs/**': reference
components:
  token_counter: process-counter
extension_runtime:
  token_counters:
    process-counter:
      command: {_command_yaml_with_args(script, calls_path)}
""",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    section_count = 15
    document_count = 4
    for index in range(document_count):
        content = "\n\n".join(f"## Section {section}\n\nBody {section}." for section in range(section_count))
        (docs / f"guide-{index}.md").write_text(f"# Guide {index}\n\n{content}\n", encoding="utf-8")

    report = _run_json(["check", str(tmp_path), "--format", "json"])

    process_invocations = int(calls_path.read_text(encoding="utf-8"))
    token_countable_units = document_count + (document_count * (section_count + 1))
    assert report["token_counter"] == "process-counter"
    assert token_countable_units >= 60
    assert process_invocations <= 8
