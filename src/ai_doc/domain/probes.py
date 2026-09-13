from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario


class ProbeMode(StrEnum):
    PLAN = "plan"


class ProbeExpectationKind(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class ProbeExpectationOutcome(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
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


class PlanningProbeReport(BaseModel):
    observations: list[VerifiedObservation] = Field(default_factory=list)

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


class ObservationVerifier(Protocol):
    def verify(
        self,
        observation: BehavioralObservation,
        scenario: EvaluationScenario,
    ) -> list[ProbeExpectationResult]: ...
