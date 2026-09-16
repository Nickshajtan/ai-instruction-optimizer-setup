from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import Candidate, CandidateStatus
from ai_doc.extensions.transport import (
    DEFAULT_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    ProcessExtensionError,
    ProcessTransport,
)
from ai_doc.providers.semantic import SemanticResponse

EVALUATE_OPERATION = "evaluate"
ANALYZE_OPERATION = "analyze"
COUNT_TOKENS_OPERATION = "count_tokens"
RECOMMEND_OPERATION = "recommend"
COMPLETE_OPERATION = "complete"
__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "PROTOCOL_VERSION",
    "ProcessAnalyzer",
    "ProcessEvaluator",
    "ProcessExtensionError",
    "ProcessRecommendationPolicy",
    "ProcessSemanticProvider",
    "ProcessTokenCounter",
    "ProcessTransport",
]


class ProcessInvoker(Protocol):
    def invoke(self, operation: str, payload: Mapping[str, Any]) -> Any: ...


class ProcessAnalyzer:
    def __init__(self, transport: ProcessInvoker) -> None:
        self.transport = transport

    def analyze(self, context: AnalysisContext) -> list[Finding]:
        result = self.transport.invoke(
            ANALYZE_OPERATION,
            {
                "payload_version": 1,
                "documents": _snapshot_payload(context.snapshot)["documents"],
                "graph": {
                    document.relative_path: {
                        "outgoing": context.graph.outgoing(document),
                        "incoming": context.graph.incoming(document),
                    }
                    for document in context.snapshot.documents
                },
                "configuration": context.config.model_dump(mode="json"),
            },
        )
        raw_findings = result.get("findings", result) if isinstance(result, Mapping) else result
        if not isinstance(raw_findings, list):
            raise ProcessExtensionError("Process analyzer result must be a findings list.")
        try:
            return [Finding.model_validate(item) for item in raw_findings]
        except ValidationError as exc:
            raise ProcessExtensionError(f"Process analyzer result failed schema validation:\n{exc}") from exc


class ProcessEvaluator:
    def __init__(
        self,
        transport: ProcessInvoker,
        *,
        engine: str = "process",
    ) -> None:
        self.transport = transport
        self.engine = engine

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        payload = _evaluation_payload(baseline, candidate, suite)
        result = self.transport.invoke(EVALUATE_OPERATION, payload)
        return _evaluation_result_from_result(result, self.engine)


class ProcessTokenCounter:
    def __init__(self, transport: ProcessInvoker, *, label: str = "process") -> None:
        self.transport = transport
        self.label = label

    def count(self, text: str, model: str | None = None) -> int:
        return self.count_many([text], model=model)[0]

    def count_many(self, texts: list[str], model: str | None = None) -> list[int]:
        items = [{"id": str(index), "text": text} for index, text in enumerate(texts)]
        result = self.transport.invoke(
            COUNT_TOKENS_OPERATION,
            {"payload_version": 1, "model": model, "items": items},
        )
        counts = result.get("counts") if isinstance(result, Mapping) else None
        if not isinstance(counts, Mapping):
            raise ProcessExtensionError("Process token counter result must contain a counts object.")
        output: list[int] = []
        for item in items:
            raw = counts.get(item["id"])
            if not isinstance(raw, int) or raw < 0:
                raise ProcessExtensionError(f"Invalid token count for item {item['id']!r}.")
            output.append(raw)
        return output


class ProcessRecommendationPolicy:
    def __init__(self, transport: ProcessInvoker) -> None:
        self.transport = transport

    def choose(self, baseline: Candidate, frontier: list[Candidate]) -> Candidate | None:
        result = self.transport.invoke(
            RECOMMEND_OPERATION,
            {
                "payload_version": 1,
                "baseline_id": baseline.id,
                "candidates": [candidate.model_dump(mode="json") for candidate in frontier],
            },
        )
        if not isinstance(result, Mapping):
            raise ProcessExtensionError("Process recommendation result must be an object.")
        candidate_id = result.get("candidate_id")
        reason = result.get("reason")
        if candidate_id is None:
            if isinstance(reason, str):
                baseline.evidence.recommendation_reason = reason
            return None
        if not isinstance(candidate_id, str):
            raise ProcessExtensionError("Process recommendation candidate_id must be a string or null.")
        by_id = {candidate.id: candidate for candidate in frontier}
        selected = by_id.get(candidate_id)
        if selected is None or selected.id == baseline.id:
            raise ProcessExtensionError(f"Process recommendation selected unknown candidate {candidate_id!r}.")
        if selected.status == CandidateStatus.REJECTED:
            raise ProcessExtensionError(f"Process recommendation selected rejected candidate {candidate_id!r}.")
        if isinstance(reason, str):
            selected.evidence.recommendation_reason = reason
        return selected


class ProcessSemanticProvider:
    def __init__(self, transport: ProcessInvoker) -> None:
        self.transport = transport

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        result = self.transport.invoke(
            COMPLETE_OPERATION,
            {"payload_version": 1, "operation": operation, "payload": payload},
        )
        try:
            return SemanticResponse.model_validate(result)
        except ValidationError as exc:
            raise ProcessExtensionError(f"Process provider result failed schema validation:\n{exc}") from exc


def _evaluation_payload(
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot | None,
    suite: EvaluationSuite,
) -> dict[str, object]:
    return {
        "baseline": _snapshot_payload(baseline),
        "candidate": _snapshot_payload(candidate) if candidate is not None else None,
        "suite": suite.model_dump(mode="json"),
    }


def _snapshot_payload(snapshot: DocumentationSnapshot) -> dict[str, object]:
    return {
        "root": str(snapshot.root),
        "total_tokens": snapshot.total_tokens,
        "documents": [
            {
                "path": document.relative_path,
                "profile": document.profile.value,
                "text": document.text,
                "token_count": document.token_count,
            }
            for document in snapshot.documents
        ],
    }


def _evaluation_result_from_result(
    result: Any,
    default_engine: str,
) -> EvaluationResult:
    normalized = result
    if isinstance(result, Mapping):
        normalized = {"engine": default_engine, **result}
    try:
        return EvaluationResult.model_validate(normalized)
    except ValidationError as exc:
        raise ProcessExtensionError(f"Process extension result failed schema validation:\n{exc}") from exc
