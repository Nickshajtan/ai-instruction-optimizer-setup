from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.scores import ScoreSet


class EvaluationScenario(BaseModel):
    id: str
    profile: str = "generic"
    task: str
    expected_required: list[str] = Field(default_factory=list)
    expected_forbidden: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvaluationSuite(BaseModel):
    scenarios: list[EvaluationScenario] = Field(default_factory=list)


class EvaluationCaseResult(BaseModel):
    id: str
    passed: bool
    score: float | None = None
    message: str | None = None


class EvaluationResult(BaseModel):
    engine: str
    passed: bool
    cases: list[EvaluationCaseResult] = Field(default_factory=list)
    raw_summary: dict[str, object] = Field(default_factory=dict)


class Evaluator(Protocol):
    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult: ...


class CandidateComparison(BaseModel):
    baseline: ScoreSet
    candidate: ScoreSet
    clarity_delta: float | None
    task_success_delta: float | None
    token_delta: int
    token_delta_percent: float
    expected_context_delta: float | None = None
    estimated_cost_delta: Decimal | None = None
    invariant_regressions: list[str] = Field(default_factory=list)
    recommendation: Literal["accept", "review", "reject"]
