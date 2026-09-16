from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.extensions.transport import (
    DEFAULT_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    ProcessExtensionError,
    ProcessTransport,
)

EVALUATE_OPERATION = "evaluate"
__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "PROTOCOL_VERSION",
    "ProcessEvaluator",
    "ProcessExtensionError",
    "ProcessTransport",
]


class ProcessInvoker(Protocol):
    def invoke(self, operation: str, payload: Mapping[str, Any]) -> Any: ...


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
