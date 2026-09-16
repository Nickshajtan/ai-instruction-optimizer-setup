from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.domain.optimization import Candidate
from ai_doc.extensions.transport import ProcessExtensionError

PAYLOAD_VERSION = 1


class VersionedWireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_version: int = PAYLOAD_VERSION

    @model_validator(mode="after")
    def _check_payload_version(self) -> VersionedWireModel:
        if self.payload_version != PAYLOAD_VERSION:
            raise ValueError(f"Unsupported payload_version: {self.payload_version!r}")
        return self


class WireDocumentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    profile: str
    text: str
    token_count: int


class WireSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str
    total_tokens: int
    documents: list[WireDocumentV1]


class WireDocumentGraphV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outgoing: list[str] = Field(default_factory=list)
    incoming: list[str] = Field(default_factory=list)


class AnalyzerRequestV1(VersionedWireModel):
    documents: list[WireDocumentV1]
    graph: dict[str, WireDocumentGraphV1]
    analysis: dict[str, Any] = Field(default_factory=dict)


class AnalyzerResultV1(VersionedWireModel):
    findings: list[dict[str, Any]]


class EvaluationRequestV1(VersionedWireModel):
    baseline: WireSnapshotV1
    candidate: WireSnapshotV1 | None = None
    suite: dict[str, Any]


class TokenCountItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str


class TokenCountRequestV1(VersionedWireModel):
    model: str | None = None
    items: list[TokenCountItemV1]


class TokenCountResultV1(VersionedWireModel):
    counts: dict[str, int]


class RecommendationCandidateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    generation: int
    objective_vector: dict[str, Any] | None = None
    creation_cost: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecommendationRequestV1(VersionedWireModel):
    baseline_id: str
    candidates: list[RecommendationCandidateV1]


class RecommendationDecisionV1(VersionedWireModel):
    candidate_id: str | None = None
    reason: str | None = None


class SemanticProviderRequestV1(VersionedWireModel):
    operation: str
    payload: dict[str, Any] = Field(default_factory=dict)


def analyzer_request_from_context(context: AnalysisContext) -> dict[str, Any]:
    request = AnalyzerRequestV1(
        documents=_wire_documents(context.snapshot),
        graph={
            document.relative_path: WireDocumentGraphV1(
                outgoing=context.graph.outgoing(document),
                incoming=context.graph.incoming(document),
            )
            for document in context.snapshot.documents
        },
        analysis={
            "budgets": {
                profile.value: {
                    "warning_tokens": budget.warning_tokens,
                    "error_tokens": budget.error_tokens,
                }
                for profile, budget in context.config.budgets.items()
            }
        },
    )
    return request.model_dump(mode="json")


def evaluation_request(
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot | None,
    suite: EvaluationSuite,
) -> dict[str, Any]:
    request = EvaluationRequestV1(
        baseline=snapshot_to_wire(baseline),
        candidate=snapshot_to_wire(candidate) if candidate is not None else None,
        suite=suite.model_dump(mode="json"),
    )
    return request.model_dump(mode="json")


def token_count_request(texts: list[str], model: str | None) -> tuple[dict[str, Any], list[str]]:
    ids = [str(index) for index in range(len(texts))]
    request = TokenCountRequestV1(
        model=model,
        items=[TokenCountItemV1(id=item_id, text=text) for item_id, text in zip(ids, texts, strict=True)],
    )
    return request.model_dump(mode="json"), ids


def recommendation_request(baseline: Candidate, frontier: list[Candidate]) -> dict[str, Any]:
    request = RecommendationRequestV1(
        baseline_id=baseline.id,
        candidates=[candidate_to_wire(candidate) for candidate in frontier],
    )
    return request.model_dump(mode="json")


def semantic_provider_request(operation: str, payload: dict[str, object]) -> dict[str, Any]:
    return SemanticProviderRequestV1(operation=operation, payload=dict(payload)).model_dump(mode="json")


def snapshot_to_wire(snapshot: DocumentationSnapshot) -> WireSnapshotV1:
    return WireSnapshotV1(
        root=str(snapshot.root),
        total_tokens=snapshot.total_tokens,
        documents=_wire_documents(snapshot),
    )


def candidate_to_wire(candidate: Candidate) -> RecommendationCandidateV1:
    evidence: dict[str, Any] = {}
    if candidate.evidence.generation_reason is not None:
        evidence["generation_reason"] = candidate.evidence.generation_reason
    if candidate.evidence.pairwise_semantic is not None:
        evidence["pairwise_semantic"] = candidate.evidence.pairwise_semantic.model_dump(mode="json")
    if candidate.evidence.effective_context:
        evidence["effective_context"] = candidate.evidence.effective_context
    return RecommendationCandidateV1(
        id=candidate.id,
        status=candidate.status.value,
        generation=candidate.generation,
        objective_vector=(
            candidate.objective_vector.model_dump(mode="json") if candidate.objective_vector is not None else None
        ),
        creation_cost=candidate.creation_cost.model_dump(mode="json"),
        rejection_reasons=candidate.rejection_reasons,
        evidence=evidence,
    )


def validate_wire_result[WireModelT: VersionedWireModel](
    model: type[WireModelT],
    result: Any,
    message: str,
) -> WireModelT:
    try:
        return model.model_validate(result)
    except ValidationError as exc:
        raise ProcessExtensionError(f"{message} failed schema validation:\n{exc}") from exc


def validate_optional_payload_version(result: Any, message: str) -> None:
    if isinstance(result, dict) and "payload_version" in result and result["payload_version"] != PAYLOAD_VERSION:
        raise ProcessExtensionError(f"{message} has unsupported payload_version: {result['payload_version']!r}.")


def _wire_documents(snapshot: DocumentationSnapshot) -> list[WireDocumentV1]:
    return [
        WireDocumentV1(
            path=document.relative_path,
            profile=document.profile.value,
            text=document.text,
            token_count=document.token_count,
        )
        for document in snapshot.documents
    ]
