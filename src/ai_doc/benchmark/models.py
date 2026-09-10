from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class BenchmarkVariant(StrEnum):
    BASELINE = "baseline"
    CANDIDATE = "candidate"


class BenchmarkDecision(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    INCONCLUSIVE = "inconclusive"


class RunMetadata(BaseModel):
    agent: str = "generic"
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    seed: int | None = None
    environment: dict[str, str] = Field(default_factory=dict)


class TaskRun(BaseModel):
    run_id: str
    variant: BenchmarkVariant
    success: bool
    instruction_violations: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    score: float | None = None
    metadata: RunMetadata = Field(default_factory=RunMetadata)


class BenchmarkCase(BaseModel):
    id: str
    repository: str
    task: str
    tags: list[str] = Field(default_factory=list)
    runs: list[TaskRun]

    @model_validator(mode="after")
    def require_both_variants(self) -> BenchmarkCase:
        variants = {run.variant for run in self.runs}
        if BenchmarkVariant.BASELINE not in variants or BenchmarkVariant.CANDIDATE not in variants:
            raise ValueError("benchmark case requires baseline and candidate runs")
        return self


class BenchmarkSuite(BaseModel):
    schema_version: int = 1
    cases: list[BenchmarkCase]


class MetricSummary(BaseModel):
    samples: int
    mean: float
    stddev: float


class VariantSummary(BaseModel):
    runs: int
    task_success: MetricSummary
    instruction_violations: MetricSummary
    retries: MetricSummary
    input_tokens: MetricSummary
    output_tokens: MetricSummary
    latency_ms: MetricSummary | None = None
    cost_usd: MetricSummary | None = None
    score: MetricSummary | None = None


class DeltaEvidence(BaseModel):
    mean_delta: float
    stddev: float
    ci95_low: float
    ci95_high: float
    paired_samples: int


class BenchmarkCaseReport(BaseModel):
    id: str
    repository: str
    task: str
    baseline: VariantSummary
    candidate: VariantSummary
    task_success_delta: DeltaEvidence
    decision: BenchmarkDecision
    decision_reason: str


class BenchmarkReport(BaseModel):
    schema_version: int = 1
    minimum_meaningful_improvement: float
    minimum_runs: int
    cases: list[BenchmarkCaseReport]
    improved: int
    regressed: int
    inconclusive: int
