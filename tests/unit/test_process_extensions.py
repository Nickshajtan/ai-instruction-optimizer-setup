from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.domain.optimization import Candidate, CandidateCost, CandidateStatus, ObjectiveVector
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.extensions.process import (
    PROTOCOL_VERSION,
    ProcessAnalyzer,
    ProcessEvaluator,
    ProcessExtensionError,
    ProcessRecommendationPolicy,
    ProcessSemanticProvider,
    ProcessTokenCounter,
    ProcessTransport,
)
from ai_doc.markdown.graph import DocumentGraph


def _snapshot(text: str = "docs") -> DocumentationSnapshot:
    return DocumentationSnapshot.model_validate(
        {
            "root": ".",
            "documents": [
                {
                    "path": "AGENTS.md",
                    "relative_path": "AGENTS.md",
                    "profile": "instruction",
                    "text": text,
                    "token_count": 4,
                }
            ],
        }
    )


def _suite() -> EvaluationSuite:
    return EvaluationSuite.model_validate(
        {
            "scenarios": [
                {
                    "id": "smoke",
                    "profile": "coding-task",
                    "task": "Read docs.",
                    "expected_required": ["cite docs"],
                    "expected_forbidden": ["skip docs"],
                    "behavior_required": ["open file"],
                    "behavior_forbidden": ["guess"],
                    "tags": ["smoke"],
                }
            ]
        }
    )


def _candidate(candidate_id: str, status: CandidateStatus = CandidateStatus.VALID) -> Candidate:
    return Candidate(
        id=candidate_id,
        strategy="test",
        proposal=CandidateProposal(operations=[]),
        objective_vector=ObjectiveVector(
            reliability=None,
            clarity=0.8,
            always_loaded_tokens=10,
            critical_invariant_recall=1.0,
        ),
        status=status,
        generation=1,
        creation_cost=CandidateCost(generation_requests=1, generation_input_tokens=2),
        artifact_dir=f".ai-doc-output/{candidate_id}",
    )


def _transport_script(tmp_path: Path, mode: str) -> Path:
    script = tmp_path / f"transport_{mode}.py"
    script.write_text(
        f"""
from __future__ import annotations

import json
import sys
import time

mode = {mode!r}
request = sys.stdin.read()

if mode == "timeout":
    time.sleep(2)
if mode == "nonzero":
    print("boom", file=sys.stderr)
    raise SystemExit(9)
if mode == "invalid-json":
    print("not json")
    raise SystemExit(0)
if mode == "long-stderr":
    print("x" * 5000, file=sys.stderr)
    raise SystemExit(9)
if mode == "non-object":
    print("[]")
    raise SystemExit(0)

data = json.loads(request)
protocol = data["protocol"]
request_id = data["request_id"]
if mode == "wrong-protocol":
    protocol = "ai-doc.extension/v999"
if mode == "wrong-request-id":
    request_id = "wrong"

response = {{"protocol": protocol, "request_id": request_id}}
if mode == "invalid-status":
    response.update({{"status": "maybe", "result": {{}}}})
elif mode == "explicit-error":
    print("provider diagnostics", file=sys.stderr)
    response.update({{"status": "error", "error": {{"code": "provider_unavailable", "message": "offline"}}}})
elif mode == "missing-result":
    response.update({{"status": "ok"}})
elif data["operation"] == "evaluate":
    scenario_id = data["payload"]["suite"]["scenarios"][0]["id"]
    response.update(
        {{
            "status": "ok",
            "result": {{
                "payload_version": 1,
                "passed": True,
                "cases": [{{"id": scenario_id, "passed": True, "score": 0.9}}],
            }},
        }}
    )
else:
    response.update(
        {{
            "status": "ok",
            "result": {{
                "operation": data["operation"],
                "protocol": data["protocol"],
                "request_id": data["request_id"],
                "payload": data["payload"],
            }},
        }}
    )
print(json.dumps(response))
""",
        encoding="utf-8",
    )
    return script


def _transport(tmp_path: Path, mode: str, timeout: float = 1) -> ProcessTransport:
    return ProcessTransport([sys.executable, str(_transport_script(tmp_path, mode))], timeout=timeout)


def test_process_transport_invokes_generic_operation(tmp_path: Path) -> None:
    result = _transport(tmp_path, "ok").invoke("test-operation", {"value": 42})

    assert result["operation"] == "test-operation"
    assert result["protocol"] == PROTOCOL_VERSION
    assert result["request_id"]
    assert result["payload"] == {"value": 42}


def test_process_transport_can_query_describe_manifest(tmp_path: Path) -> None:
    result = _transport(tmp_path, "ok").describe()

    assert result["operation"] == "describe"


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("nonzero", "exited with status 9"),
        ("invalid-json", "invalid JSON"),
        ("non-object", "response must be a JSON object"),
        ("wrong-protocol", "Unsupported process extension protocol"),
        ("wrong-request-id", "request_id did not match"),
        ("invalid-status", "status must be 'ok' or 'error'"),
        ("explicit-error", "provider_unavailable"),
        ("missing-result", "must contain a result"),
    ],
)
def test_process_transport_reports_protocol_and_infrastructure_failures(
    tmp_path: Path,
    mode: str,
    message: str,
) -> None:
    with pytest.raises(ProcessExtensionError, match=message):
        _transport(tmp_path, mode).invoke("test-operation", {"value": 42})


def test_process_transport_reports_missing_executable() -> None:
    with pytest.raises(ProcessExtensionError, match="could not start"):
        ProcessTransport(["missing-ai-doc-extension-executable"]).invoke("test-operation", {})


def test_process_transport_reports_timeout(tmp_path: Path) -> None:
    with pytest.raises(ProcessExtensionError, match="timed out"):
        _transport(tmp_path, "timeout", timeout=0.01).invoke("test-operation", {})


def test_process_transport_includes_stderr_diagnostics(tmp_path: Path) -> None:
    with pytest.raises(ProcessExtensionError, match="Diagnostics:\nboom"):
        _transport(tmp_path, "nonzero").invoke("test-operation", {})


def test_process_transport_limits_stderr_diagnostics(tmp_path: Path) -> None:
    with pytest.raises(ProcessExtensionError) as exc_info:
        _transport(tmp_path, "long-stderr").invoke("test-operation", {})

    assert exc_info.value.diagnostics == "x" * 4000


class FakeTransport:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, object]]] = []

    def invoke(self, operation: str, payload: dict[str, object]) -> Any:
        self.calls.append((operation, payload))
        return self.result


def test_process_evaluator_maps_domain_payload_to_evaluate_operation() -> None:
    transport = FakeTransport(
        {"payload_version": 1, "passed": True, "cases": [{"id": "smoke", "passed": True, "score": 0.9}]}
    )
    evaluator = ProcessEvaluator(transport, engine="instruction-quality")

    result = evaluator.evaluate(_snapshot("baseline"), _snapshot("candidate"), _suite())

    operation, payload = transport.calls[0]
    baseline = payload["baseline"]
    candidate = payload["candidate"]
    suite = payload["suite"]
    assert operation == "evaluate"
    assert isinstance(baseline, dict)
    assert isinstance(candidate, dict)
    assert isinstance(suite, dict)
    assert baseline["documents"][0]["text"] == "baseline"
    assert candidate["documents"][0]["text"] == "candidate"
    assert sorted(payload) == ["baseline", "candidate", "payload_version", "suite"]
    assert sorted(suite) == ["scenarios"]
    assert suite["scenarios"][0] == {
        "id": "smoke",
        "profile": "coding-task",
        "task": "Read docs.",
        "expected_required": ["cite docs"],
        "expected_forbidden": ["skip docs"],
        "behavior_required": ["open file"],
        "behavior_forbidden": ["guess"],
        "tags": ["smoke"],
    }
    assert result.engine == "instruction-quality"
    assert result.passed is True
    assert result.cases[0].id == "smoke"


def test_process_evaluator_preserves_engine_returned_by_extension() -> None:
    transport = FakeTransport({"payload_version": 1, "engine": "external-fixture", "passed": True, "cases": []})
    evaluator = ProcessEvaluator(transport, engine="instruction-quality")

    result = evaluator.evaluate(_snapshot(), None, _suite())

    assert result.engine == "external-fixture"


def test_process_evaluator_reports_invalid_result_schema_without_subprocess() -> None:
    evaluator = ProcessEvaluator(FakeTransport({"payload_version": 1, "passed": True, "cases": [{}]}))

    with pytest.raises(ProcessExtensionError, match="schema validation"):
        evaluator.evaluate(_snapshot(), None, _suite())


def test_process_evaluator_rejects_bad_payload_version_result() -> None:
    evaluator = ProcessEvaluator(FakeTransport({"payload_version": 2, "passed": True, "cases": []}))

    with pytest.raises(ProcessExtensionError, match="payload_version"):
        evaluator.evaluate(_snapshot(), None, _suite())


def test_process_evaluator_runs_end_to_end_with_process_transport(tmp_path: Path) -> None:
    transport = _transport(tmp_path, "ok")
    evaluator = ProcessEvaluator(transport, engine="process")

    result = evaluator.evaluate(_snapshot(), None, _suite())

    assert result.engine == "process"
    assert result.passed is True
    assert result.cases[0].id == "smoke"


def test_process_analyzer_payload_exposes_intentional_shape_not_full_config() -> None:
    transport = FakeTransport({"payload_version": 1, "findings": []})
    analyzer = ProcessAnalyzer(transport)
    snapshot = _snapshot("docs")
    context = AnalysisContext(
        config=DEFAULT_CONFIG,
        snapshot=snapshot,
        graph=DocumentGraph(snapshot),
    )

    assert analyzer.analyze(context) == []

    _, payload = transport.calls[0]
    assert payload["payload_version"] == 1
    assert sorted(payload) == ["analysis", "documents", "graph", "payload_version"]
    assert "configuration" not in payload
    assert "extension_runtime" not in payload
    assert payload["documents"][0] == {
        "path": "AGENTS.md",
        "profile": "instruction",
        "text": "docs",
        "token_count": 4,
    }


def test_process_analyzer_rejects_malformed_result_schema() -> None:
    analyzer = ProcessAnalyzer(FakeTransport({"payload_version": 1, "findings": [{"code": "BROKEN"}]}))
    snapshot = _snapshot("docs")
    context = AnalysisContext(config=DEFAULT_CONFIG, snapshot=snapshot, graph=DocumentGraph(snapshot))

    with pytest.raises(ProcessExtensionError, match="schema validation"):
        analyzer.analyze(context)


def test_process_analyzer_rejects_bad_payload_version_result() -> None:
    analyzer = ProcessAnalyzer(FakeTransport({"payload_version": 2, "findings": []}))
    snapshot = _snapshot("docs")
    context = AnalysisContext(config=DEFAULT_CONFIG, snapshot=snapshot, graph=DocumentGraph(snapshot))

    with pytest.raises(ProcessExtensionError, match="payload_version"):
        analyzer.analyze(context)


def test_process_token_counter_rejects_bad_payload_version_result() -> None:
    counter = ProcessTokenCounter(FakeTransport({"payload_version": 2, "counts": {"0": 1}}))

    with pytest.raises(ProcessExtensionError, match="payload_version"):
        counter.count("hello")


def test_process_token_counter_rejects_malformed_counts() -> None:
    counter = ProcessTokenCounter(FakeTransport({"payload_version": 1, "counts": {"0": -1}}))

    with pytest.raises(ProcessExtensionError, match="Invalid token count"):
        counter.count("hello")


def test_process_recommendation_payload_exposes_intentional_candidate_shape() -> None:
    baseline = _candidate("baseline", CandidateStatus.FRONTIER)
    selected = _candidate("C001")
    transport = FakeTransport({"payload_version": 1, "candidate_id": "C001", "reason": "external reason"})
    policy = ProcessRecommendationPolicy(transport)

    assert policy.choose(baseline, [baseline, selected]) is selected

    _, payload = transport.calls[0]
    candidate_payload = payload["candidates"][1]
    assert sorted(candidate_payload) == [
        "creation_cost",
        "evidence",
        "generation",
        "id",
        "objective_vector",
        "rejection_reasons",
        "status",
    ]
    assert "artifact_dir" not in candidate_payload
    assert "proposal" not in candidate_payload
    assert selected.evidence.recommendation_reason == "external reason"
    assert baseline.evidence.recommendation_reason is None
    assert policy.last_decision is not None
    assert policy.last_decision.reason == "external reason"


def test_process_recommendation_rejects_bad_payload_version_result() -> None:
    policy = ProcessRecommendationPolicy(FakeTransport({"payload_version": 2, "candidate_id": None}))

    with pytest.raises(ProcessExtensionError, match="payload_version"):
        policy.choose(_candidate("baseline", CandidateStatus.FRONTIER), [])


def test_process_recommendation_rejects_malformed_result_schema() -> None:
    policy = ProcessRecommendationPolicy(FakeTransport({"payload_version": 1, "candidate_id": 123}))

    with pytest.raises(ProcessExtensionError, match="schema validation"):
        policy.choose(_candidate("baseline", CandidateStatus.FRONTIER), [])


def test_process_provider_rejects_bad_payload_version_result() -> None:
    provider = ProcessSemanticProvider(FakeTransport({"payload_version": 2, "data": {}, "usage": {}}))

    with pytest.raises(ProcessExtensionError, match="payload_version"):
        provider.invoke("generate_candidate", {})


def test_process_provider_rejects_malformed_result_schema() -> None:
    provider = ProcessSemanticProvider(
        FakeTransport({"payload_version": 1, "data": {}, "usage": {"requests": "many"}})
    )

    with pytest.raises(ProcessExtensionError, match="schema validation"):
        provider.invoke("generate_candidate", {})
