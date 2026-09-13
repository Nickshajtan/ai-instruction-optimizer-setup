from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario


class ProbeMode(StrEnum):
    PLAN = "plan"
    EXECUTE = "execute"


class ProbeExpectationKind(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class ProbeExpectationOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNCERTAIN = "uncertain"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"


class ProbeUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)


class BehavioralObservation(BaseModel):
    target: str
    model: str | None = None
    model_version: str | None = None
    scenario_id: str
    mode: ProbeMode = ProbeMode.PLAN
    context_paths: list[str] = Field(default_factory=list)
    applicable_rules: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    forbidden_actions_avoided: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    usage: ProbeUsage = Field(default_factory=ProbeUsage)
    cache_key: str | None = None
    raw_summary: dict[str, object] = Field(default_factory=dict)


class WorkspaceDelta(BaseModel):
    created_paths: list[str] = Field(default_factory=list)
    modified_paths: list[str] = Field(default_factory=list)
    deleted_paths: list[str] = Field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return sorted({*self.created_paths, *self.modified_paths, *self.deleted_paths})


class ExecutionObservation(BaseModel):
    target: str
    model: str | None = None
    model_version: str | None = None
    scenario_id: str
    mode: ProbeMode = ProbeMode.EXECUTE
    context_paths: list[str] = Field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.UNCERTAIN
    performed_actions: list[str] = Field(default_factory=list)
    forbidden_actions_avoided: list[str] = Field(default_factory=list)
    reported_checks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    workspace_delta: WorkspaceDelta = Field(default_factory=WorkspaceDelta)
    usage: ProbeUsage = Field(default_factory=ProbeUsage)
    cache_key: str | None = None
    raw_summary: dict[str, object] = Field(default_factory=dict)


class ProbeExpectationResult(BaseModel):
    expectation: str
    kind: ProbeExpectationKind
    outcome: ProbeExpectationOutcome
    evidence: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verifier: str


class VerifiedObservation(BaseModel):
    observation: BehavioralObservation
    expectations: list[ProbeExpectationResult] = Field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(item.outcome == ProbeExpectationOutcome.VIOLATED for item in self.expectations)

    @property
    def satisfied(self) -> int:
        return sum(item.outcome == ProbeExpectationOutcome.SATISFIED for item in self.expectations)


class VerifiedExecutionObservation(BaseModel):
    observation: ExecutionObservation
    expectations: list[ProbeExpectationResult] = Field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(item.outcome == ProbeExpectationOutcome.VIOLATED for item in self.expectations)

    @property
    def satisfied(self) -> int:
        return sum(item.outcome == ProbeExpectationOutcome.SATISFIED for item in self.expectations)


class PlanningProbeReport(BaseModel):
    observations: list[VerifiedObservation] = Field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(item.violations for item in self.observations)

    @property
    def satisfied(self) -> int:
        return sum(item.satisfied for item in self.observations)


class ExecutionProbeReport(BaseModel):
    observations: list[VerifiedExecutionObservation] = Field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(item.violations for item in self.observations)

    @property
    def satisfied(self) -> int:
        return sum(item.satisfied for item in self.observations)


class ScenarioProbeComparison(BaseModel):
    scenario_id: str
    baseline_violations: int
    candidate_violations: int
    baseline_satisfied: int
    candidate_satisfied: int


class PlanningProbeComparison(BaseModel):
    baseline: PlanningProbeReport
    candidate: PlanningProbeReport
    scenarios: list[ScenarioProbeComparison] = Field(default_factory=list)


class TargetProbe(Protocol):
    def run(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> BehavioralObservation: ...


class ExecutionProbe(Protocol):
    def run(
        self,
        workspace_root: Path,
        snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation: ...


class ObservationVerifier(Protocol):
    def verify(
        self,
        observation: BehavioralObservation,
        scenario: EvaluationScenario,
    ) -> list[ProbeExpectationResult]: ...


class ExecutionObservationVerifier(Protocol):
    def verify(
        self,
        observation: ExecutionObservation,
        scenario: EvaluationScenario,
    ) -> list[ProbeExpectationResult]: ...
