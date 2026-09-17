from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import Candidate, CandidateStatus
from ai_doc.extensions.contracts import (
    AnalyzerResultV1,
    EvaluationResultV1,
    RecommendationDecisionV1,
    SemanticProviderResultV1,
    TokenCountResultV1,
    analyzer_request_from_context,
    evaluation_request,
    recommendation_request,
    semantic_provider_request,
    token_count_request,
    validate_wire_result,
)
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
        result = self.transport.invoke(ANALYZE_OPERATION, analyzer_request_from_context(context))
        raw_findings = validate_wire_result(AnalyzerResultV1, result, "Process analyzer result").findings
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
        payload = evaluation_request(baseline, candidate, suite)
        result = self.transport.invoke(EVALUATE_OPERATION, payload)
        return _evaluation_result_from_result(result, self.engine)


class ProcessTokenCounter:
    def __init__(self, transport: ProcessInvoker, *, label: str = "process") -> None:
        self.transport = transport
        self.label = label

    def count(self, text: str, model: str | None = None) -> int:
        return self.count_many([text], model=model)[0]

    def count_many(self, texts: list[str], model: str | None = None) -> list[int]:
        payload, item_ids = token_count_request(texts, model)
        result = self.transport.invoke(COUNT_TOKENS_OPERATION, payload)
        counts = validate_wire_result(TokenCountResultV1, result, "Process token counter result").counts
        output: list[int] = []
        for item_id in item_ids:
            raw = counts.get(item_id)
            if not isinstance(raw, int) or raw < 0:
                raise ProcessExtensionError(f"Invalid token count for item {item_id!r}.")
            output.append(raw)
        return output


class ProcessRecommendationPolicy:
    def __init__(self, transport: ProcessInvoker) -> None:
        self.transport = transport
        self.last_decision: RecommendationDecisionV1 | None = None

    def choose(self, baseline: Candidate, frontier: list[Candidate]) -> Candidate | None:
        result = self.transport.invoke(RECOMMEND_OPERATION, recommendation_request(baseline, frontier))
        decision = validate_wire_result(RecommendationDecisionV1, result, "Process recommendation result")
        self.last_decision = decision
        candidate_id = decision.candidate_id
        if candidate_id is None:
            baseline.evidence.recommendation_reason = decision.reason
            return None
        by_id = {candidate.id: candidate for candidate in frontier}
        selected = by_id.get(candidate_id)
        if selected is None or selected.id == baseline.id:
            raise ProcessExtensionError(f"Process recommendation selected unknown candidate {candidate_id!r}.")
        if selected.status == CandidateStatus.REJECTED:
            raise ProcessExtensionError(f"Process recommendation selected rejected candidate {candidate_id!r}.")
        selected.evidence.recommendation_reason = decision.reason
        return selected


class ProcessSemanticProvider:
    def __init__(self, transport: ProcessInvoker) -> None:
        self.transport = transport

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        result = self.transport.invoke(COMPLETE_OPERATION, semantic_provider_request(operation, payload))
        wire_result = validate_wire_result(SemanticProviderResultV1, result, "Process provider result")
        try:
            return SemanticResponse.model_validate(wire_result.model_dump(mode="json", exclude={"payload_version"}))
        except ValidationError as exc:
            raise ProcessExtensionError(f"Process provider result failed schema validation:\n{exc}") from exc

def _evaluation_result_from_result(
    result: Any,
    default_engine: str,
) -> EvaluationResult:
    if not isinstance(result, Mapping):
        raise ProcessExtensionError("Process evaluator result must be an object.")
    wire_result = validate_wire_result(EvaluationResultV1, result, "Process evaluator result")
    normalized = wire_result.model_dump(mode="json", exclude={"payload_version"})
    if normalized.get("engine") is None:
        normalized["engine"] = default_engine
    try:
        return EvaluationResult.model_validate(normalized)
    except ValidationError as exc:
        raise ProcessExtensionError(f"Process extension result failed schema validation:\n{exc}") from exc
