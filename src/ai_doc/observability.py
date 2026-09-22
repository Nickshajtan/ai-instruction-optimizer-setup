from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field

from ai_doc import __version__
from ai_doc.config.models import AiDocConfig
from ai_doc.domain.evaluations import EvaluationResult, PairwiseOutcome
from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import CandidateCost, OptimizationRun
from ai_doc.reporting.models import CheckReport, SearchOptimizeReport

OBSERVATION_SCHEMA = "ai-doc.observation/v1"
HASH_PREFIX_LENGTH = 16
WARNING_PREFIX = "Observation logging failed:"
TOKEN_SEMANTICS_REPORTED = "reported"


class ObservationWriteError(RuntimeError):
    pass


class ObservationTimer:
    def __init__(self) -> None:
        self.timestamp = datetime.now(UTC)
        self._started = perf_counter()

    def duration_ms(self) -> int:
        return max(0, round((perf_counter() - self._started) * 1000))


class TierObservation(BaseModel):
    tier: str
    component: str
    status: str
    duration_ms: int | None = None
    finding_count: int | None = None
    outcome: str | None = None


class FindingObservation(BaseModel):
    fingerprint: str
    tier: str
    rule: str
    category: str
    severity: str
    document: str
    section: str | None = None


class ProviderObservation(BaseModel):
    operation: str
    requests: int
    input_tokens: int
    output_tokens: int
    cache_hits: int | None = None
    token_semantics: str
    cost_usd: Decimal | None = None
    cost_source: str | None = None


class EvaluationObservation(BaseModel):
    tier: str
    engine: str
    passed: bool
    case_count: int
    failed_case_count: int


class OptimizationObservation(BaseModel):
    strategy: str
    candidates_generated: int
    candidates_evaluated: int
    candidates_rejected: int
    pareto_candidate_count: int
    final_candidate_id: str | None = None
    termination_reason: str
    repair_rounds: int | None = None
    pairwise: PairwiseObservation | None = None


class PairwiseObservation(BaseModel):
    requested: bool
    comparisons_performed: int
    skipped_not_needed: int = 0
    candidate_preferred: int = 0
    baseline_preferred: int = 0
    equivalent: int = 0
    uncertain: int = 0


class ProbeObservation(BaseModel):
    scenarios: int
    passed: int | None = None
    failed: int | None = None


class ObservationContext(BaseModel):
    project_fingerprint: str
    config_fingerprint: str
    document_count: int | None = None


class ObservationRecord(BaseModel):
    schema_id: str = Field(default=OBSERVATION_SCHEMA, alias="schema")
    run_id: str
    timestamp: str
    tool_version: str
    command: str
    status: str
    duration_ms: int
    exit_code: int | None = None
    context: ObservationContext
    tiers: list[TierObservation] = Field(default_factory=list)
    findings: list[FindingObservation] = Field(default_factory=list)
    evaluations: list[EvaluationObservation] = Field(default_factory=list)
    providers: list[ProviderObservation] = Field(default_factory=list)
    optimization: OptimizationObservation | None = None
    probes: ProbeObservation | None = None


def new_run_id() -> str:
    return uuid.uuid4().hex


def observation_path(root: Path, config: AiDocConfig) -> Path:
    configured = Path(config.observability.path)
    base = root.resolve()
    path = configured if configured.is_absolute() else base / configured
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(base)
    except (OSError, ValueError) as exc:
        raise ObservationWriteError(
            f"Observation path must stay inside the project root: {config.observability.path}"
        ) from exc
    return resolved


def append_observation(root: Path, config: AiDocConfig, record: ObservationRecord) -> None:
    if not config.observability.enabled:
        return
    path: Path | str = config.observability.path
    try:
        path = observation_path(root, config)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(record.model_dump_json(by_alias=True) + "\n")
    except (ObservationWriteError, OSError) as exc:
        raise ObservationWriteError(f"{path}: {exc}") from exc


def observation_context(root: Path, config: AiDocConfig, document_count: int | None) -> ObservationContext:
    return ObservationContext(
        project_fingerprint=_hash_text(root.resolve().as_posix()),
        config_fingerprint=_hash_text(config.model_dump_json(exclude={"observability"})),
        document_count=document_count,
    )


def check_observation(
    *,
    run_id: str,
    timer: ObservationTimer,
    root: Path,
    config: AiDocConfig,
    report: CheckReport,
    status: str,
    exit_code: int,
    static_duration_ms: int | None,
    deep_duration_ms: int | None = None,
) -> ObservationRecord:
    tiers = [
        TierObservation(
            tier="a0",
            component="static",
            status="completed",
            duration_ms=static_duration_ms,
            finding_count=len(report.findings),
            outcome="findings" if report.findings else "no_findings",
        )
    ]
    evaluations: list[EvaluationObservation] = []
    if report.evaluation is not None:
        tiers.append(
            TierObservation(
                tier="b",
                component=report.evaluation.engine,
                status="completed",
                duration_ms=deep_duration_ms,
                outcome="passed" if report.evaluation.passed else "failed",
            )
        )
        evaluations.append(_evaluation_observation("b", report.evaluation))
    return ObservationRecord(
        run_id=run_id,
        timestamp=timer.timestamp.isoformat().replace("+00:00", "Z"),
        tool_version=__version__,
        command="check",
        status=status,
        duration_ms=timer.duration_ms(),
        exit_code=exit_code,
        context=observation_context(root, config, report.files_analyzed),
        tiers=tiers,
        findings=[finding_observation(finding, "a0") for finding in report.findings],
        evaluations=evaluations,
    )


def optimize_observation(
    *,
    timer: ObservationTimer,
    root: Path,
    config: AiDocConfig,
    report: SearchOptimizeReport,
    status: str,
    exit_code: int,
    static_duration_ms: int | None,
    optimize_duration_ms: int | None,
) -> ObservationRecord:
    run = report.run
    tiers = [
        TierObservation(
            tier="a0",
            component="static",
            status="completed",
            duration_ms=static_duration_ms,
            finding_count=len(report.baseline.findings),
            outcome="findings" if report.baseline.findings else "no_findings",
        ),
        TierObservation(
            tier="optimizer",
            component=str(run.strategy),
            status="completed",
            duration_ms=optimize_duration_ms,
            outcome=str(run.stopped_reason),
        ),
    ]
    evaluations = _candidate_evaluations(run)
    if evaluations:
        tiers.append(
            TierObservation(
                tier="b",
                component="semantic-evaluation",
                status="completed",
                outcome="executed",
            )
        )
    return ObservationRecord(
        run_id=run.run_id,
        timestamp=timer.timestamp.isoformat().replace("+00:00", "Z"),
        tool_version=__version__,
        command="optimize",
        status=status,
        duration_ms=timer.duration_ms(),
        exit_code=exit_code,
        context=observation_context(root, config, report.baseline.files_analyzed),
        tiers=tiers,
        findings=[finding_observation(finding, "a0") for finding in report.baseline.findings],
        evaluations=evaluations,
        providers=_provider_observations(run.total_cost),
        optimization=_optimization_observation(report),
    )


def probe_observation(
    *,
    run_id: str,
    timer: ObservationTimer,
    root: Path,
    config: AiDocConfig,
    command: str,
    status: str,
    exit_code: int,
    document_count: int | None,
    scenario_count: int,
) -> ObservationRecord:
    return ObservationRecord(
        run_id=run_id,
        timestamp=timer.timestamp.isoformat().replace("+00:00", "Z"),
        tool_version=__version__,
        command=command,
        status=status,
        duration_ms=timer.duration_ms(),
        exit_code=exit_code,
        context=observation_context(root, config, document_count),
        tiers=[
            TierObservation(
                tier="c1" if command == "probe" else "c2",
                component=command,
                status=status,
                outcome="executed" if status == "completed" else status,
            )
        ],
        probes=ProbeObservation(scenarios=scenario_count),
    )


def failed_observation(
    *,
    run_id: str,
    timer: ObservationTimer,
    root: Path,
    config: AiDocConfig,
    command: str,
    exit_code: int,
    document_count: int | None = None,
) -> ObservationRecord:
    return ObservationRecord(
        run_id=run_id,
        timestamp=timer.timestamp.isoformat().replace("+00:00", "Z"),
        tool_version=__version__,
        command=command,
        status="failed",
        duration_ms=timer.duration_ms(),
        exit_code=exit_code,
        context=observation_context(root, config, document_count),
    )


def finding_observation(finding: Finding, tier: str) -> FindingObservation:
    document = _hash_text(finding.path)
    section = _hash_text(finding.section) if finding.section else None
    identity = "|".join([finding.code, str(finding.category), str(finding.severity), document, section or ""])
    return FindingObservation(
        fingerprint=_hash_text(identity),
        tier=tier,
        rule=finding.code,
        category=str(finding.category),
        severity=str(finding.severity),
        document=document,
        section=section,
    )


def _optimization_observation(report: SearchOptimizeReport) -> OptimizationObservation:
    run = report.run
    generated = [candidate for candidate in run.candidates if candidate.id != run.baseline_candidate_id]
    repair_rounds = sum(1 for candidate in generated if candidate.parent_ids)
    return OptimizationObservation(
        strategy=str(run.strategy),
        candidates_generated=len(generated),
        candidates_evaluated=report.candidates_evaluated,
        candidates_rejected=report.candidates_rejected,
        pareto_candidate_count=len(report.frontier),
        final_candidate_id=run.recommended_candidate_id,
        termination_reason=str(run.stopped_reason),
        repair_rounds=repair_rounds,
        pairwise=_pairwise_observation(run),
    )


def _pairwise_observation(run: OptimizationRun) -> PairwiseObservation:
    outcomes = [
        candidate.evidence.pairwise_semantic.overall
        for candidate in run.candidates
        if candidate.evidence.pairwise_semantic is not None
    ]
    return PairwiseObservation(
        requested=run.pairwise_semantic_requested,
        comparisons_performed=run.pairwise_comparisons_performed,
        skipped_not_needed=run.pairwise_comparisons_skipped_not_needed,
        candidate_preferred=sum(1 for outcome in outcomes if outcome == PairwiseOutcome.CANDIDATE),
        baseline_preferred=sum(1 for outcome in outcomes if outcome == PairwiseOutcome.BASELINE),
        equivalent=sum(1 for outcome in outcomes if outcome == PairwiseOutcome.EQUIVALENT),
        uncertain=sum(1 for outcome in outcomes if outcome == PairwiseOutcome.UNCERTAIN),
    )


def _candidate_evaluations(run: OptimizationRun) -> list[EvaluationObservation]:
    observations: list[EvaluationObservation] = []
    for candidate in run.candidates:
        if candidate.evaluation is not None:
            observations.append(_evaluation_observation("b", candidate.evaluation))
        if candidate.evidence.pairwise_semantic is not None:
            pairwise = candidate.evidence.pairwise_semantic
            observations.append(
                EvaluationObservation(
                    tier="b",
                    engine=pairwise.engine,
                    passed=pairwise.overall.value == "candidate",
                    case_count=len(pairwise.dimensions),
                    failed_case_count=sum(1 for item in pairwise.dimensions if item.outcome.value != "candidate"),
                )
            )
    return observations


def _evaluation_observation(tier: str, evaluation: EvaluationResult) -> EvaluationObservation:
    return EvaluationObservation(
        tier=tier,
        engine=evaluation.engine,
        passed=evaluation.passed,
        case_count=len(evaluation.cases),
        failed_case_count=sum(1 for case in evaluation.cases if not case.passed),
    )


def _provider_observations(cost: CandidateCost) -> list[ProviderObservation]:
    observations: list[ProviderObservation] = []
    _append_provider_usage(
        observations,
        "generation",
        cost.generation_requests,
        cost.generation_input_tokens,
        cost.generation_output_tokens,
    )
    _append_provider_usage(
        observations,
        "evaluation",
        cost.evaluation_requests,
        cost.evaluation_input_tokens,
        cost.evaluation_output_tokens,
    )
    _append_provider_usage(
        observations,
        "prompt_suboptimizer",
        cost.prompt_suboptimizer_requests,
        cost.prompt_suboptimizer_input_tokens,
        cost.prompt_suboptimizer_output_tokens,
    )
    if cost.total_cost or cost.cost_sources:
        observations.append(
            ProviderObservation(
                operation="aggregate",
                requests=cost.external_requests,
                input_tokens=cost.input_tokens,
                output_tokens=cost.output_tokens,
                cache_hits=cost.cache_hits,
                token_semantics=TOKEN_SEMANTICS_REPORTED,
                cost_usd=cost.total_cost,
                cost_source=_cost_source(cost),
            )
        )
    return observations


def _append_provider_usage(
    observations: list[ProviderObservation],
    operation: str,
    requests: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    if requests <= 0 and input_tokens <= 0 and output_tokens <= 0:
        return
    observations.append(
        ProviderObservation(
            operation=operation,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_semantics=TOKEN_SEMANTICS_REPORTED,
        )
    )


def _cost_source(cost: CandidateCost) -> str:
    unique = set(cost.cost_sources)
    if len(unique) > 1:
        return "mixed"
    if cost.cost_sources:
        return cost.cost_sources[0]
    return "unknown"


def _hash_text(value: str | None) -> str:
    data = (value or "").encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:HASH_PREFIX_LENGTH]
