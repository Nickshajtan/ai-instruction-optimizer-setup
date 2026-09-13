from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import (
    EvaluationCaseResult,
    EvaluationResult,
    EvaluationSuite,
    PairwiseDimension,
    PairwiseDimensionResult,
    PairwiseOutcome,
    PairwiseSemanticResult,
)
from ai_doc.optimizer.semantic import PAIRWISE_DIMENSIONS, uncertain_pairwise_result

DEEPEVAL_ENGINE = "deepeval"
DEEPEVAL_METRIC_PREFIX = "ai-doc"
DEEPEVAL_DEFAULT_THRESHOLD = 0.5
DEEPEVAL_CRITERIA = (
    "Evaluate whether the documentation supports the required behavior without violating forbidden behavior."
)
DEEPEVAL_REASON_ATTRIBUTE = "reason"
DEEPEVAL_SCORE_ATTRIBUTE = "score"
DEEPEVAL_PAIRWISE_ENGINE = "deepeval-arena-geval"
BASELINE_CONTESTANT = "baseline"
CANDIDATE_CONTESTANT = "candidate"


class DeepEvalUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepEvalSymbols:
    geval: Callable[..., Any]
    llm_test_case: Callable[..., Any]
    actual_output_param: object
    expected_output_param: object
    input_param: object
    arena_geval: Callable[..., Any] | None = None
    arena_test_case: Callable[..., Any] | None = None
    contestant: Callable[..., Any] | None = None


class DeepEvalEvaluator:
    """Optional semantic DeepEval adapter."""

    def __init__(self, threshold: float = DEEPEVAL_DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        symbols = _load_deepeval_symbols()
        documents = (candidate if candidate is not None else baseline).documents
        actual = "\n\n".join(document.text for document in documents)
        cases: list[EvaluationCaseResult] = []
        for scenario in suite.scenarios:
            metric = symbols.geval(
                name=f"{DEEPEVAL_METRIC_PREFIX}-{scenario.id}",
                criteria=DEEPEVAL_CRITERIA,
                evaluation_params=[
                    symbols.actual_output_param,
                    symbols.expected_output_param,
                ],
                threshold=self.threshold,
            )
            expected = [*scenario.expected_required]
            if scenario.expected_forbidden:
                expected.append("Forbidden behavior: " + "; ".join(scenario.expected_forbidden))
            test_case = symbols.llm_test_case(
                input=scenario.task,
                actual_output=actual,
                expected_output="\n".join(expected),
            )
            metric.measure(test_case)
            cases.append(
                EvaluationCaseResult(
                    id=scenario.id,
                    passed=bool(metric.is_successful()),
                    score=_metric_score(metric),
                    message=getattr(metric, DEEPEVAL_REASON_ATTRIBUTE, None),
                )
            )
        return EvaluationResult(
            engine=DEEPEVAL_ENGINE,
            passed=all(case.passed for case in cases),
            cases=cases,
            raw_summary={"semantic": True},
        )

    def compare_pairwise(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot,
        suite: EvaluationSuite,
    ) -> PairwiseSemanticResult:
        symbols = _load_deepeval_symbols()
        if symbols.arena_geval is None or symbols.arena_test_case is None or symbols.contestant is None:
            return uncertain_pairwise_result(DEEPEVAL_PAIRWISE_ENGINE, "DeepEval ArenaGEval is unavailable")
        dimensions = [
            _measure_pairwise_dimension(symbols, dimension, baseline, candidate, suite)
            for dimension in PAIRWISE_DIMENSIONS
        ]
        overall = _overall_from_dimensions(dimensions)
        return PairwiseSemanticResult(
            engine=DEEPEVAL_PAIRWISE_ENGINE,
            overall=overall,
            dimensions=dimensions,
            reason="Overall is derived from requested pairwise dimensions; uncertainty or ties remain explicit.",
            raw_summary={"semantic": True, "pairwise": True},
        )


def _load_deepeval_symbols() -> DeepEvalSymbols:
    try:
        metrics = import_module("deepeval.metrics")
        test_case = import_module("deepeval.test_case")
    except ImportError as exc:
        raise DeepEvalUnavailableError(
            "DeepEval is unavailable. Install ai-doc[deepeval] to use this evaluator."
        ) from exc
    metrics_api = cast(Any, metrics)
    test_case_api = cast(Any, test_case)
    single_turn_params = test_case_api.SingleTurnParams
    arena_geval = getattr(metrics_api, "ArenaGEval", None)
    arena_test_case = getattr(test_case_api, "ArenaTestCase", None)
    contestant = getattr(test_case_api, "Contestant", None)
    return DeepEvalSymbols(
        geval=cast(Callable[..., Any], metrics_api.GEval),
        llm_test_case=cast(Callable[..., Any], test_case_api.LLMTestCase),
        actual_output_param=single_turn_params.ACTUAL_OUTPUT,
        expected_output_param=single_turn_params.EXPECTED_OUTPUT,
        input_param=single_turn_params.INPUT,
        arena_geval=cast(Callable[..., Any] | None, arena_geval),
        arena_test_case=cast(Callable[..., Any] | None, arena_test_case),
        contestant=cast(Callable[..., Any] | None, contestant),
    )


def _metric_score(metric: object) -> float | None:
    score = getattr(metric, DEEPEVAL_SCORE_ATTRIBUTE, None)
    return float(score) if score is not None else None


def _measure_pairwise_dimension(
    symbols: DeepEvalSymbols,
    dimension: PairwiseDimension,
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot,
    suite: EvaluationSuite,
) -> PairwiseDimensionResult:
    assert symbols.arena_test_case is not None
    assert symbols.contestant is not None
    assert symbols.arena_geval is not None
    baseline_text = _snapshot_text(baseline)
    candidate_text = _snapshot_text(candidate)
    criteria = _pairwise_criteria(dimension)
    test_case = symbols.arena_test_case(
        contestants=[
            symbols.contestant(
                name=BASELINE_CONTESTANT,
                hyperparameters={"variant": BASELINE_CONTESTANT},
                test_case=symbols.llm_test_case(
                    input=_pairwise_input(suite),
                    actual_output=baseline_text,
                    expected_output=_pairwise_expected(suite),
                ),
            ),
            symbols.contestant(
                name=CANDIDATE_CONTESTANT,
                hyperparameters={"variant": CANDIDATE_CONTESTANT},
                test_case=symbols.llm_test_case(
                    input=_pairwise_input(suite),
                    actual_output=candidate_text,
                    expected_output=_pairwise_expected(suite),
                ),
            ),
        ]
    )
    metric = symbols.arena_geval(
        name=f"{DEEPEVAL_METRIC_PREFIX}-pairwise-{dimension.value}",
        criteria=criteria,
        evaluation_params=[
            symbols.input_param,
            symbols.actual_output_param,
            symbols.expected_output_param,
        ],
    )
    metric.measure(test_case)
    return PairwiseDimensionResult(
        dimension=dimension,
        outcome=_winner_to_outcome(getattr(metric, "winner", None)),
        evidence=str(getattr(metric, DEEPEVAL_REASON_ATTRIBUTE, None) or "DeepEval did not return a reason."),
    )


def _overall_from_dimensions(dimensions: list[PairwiseDimensionResult]) -> PairwiseOutcome:
    candidate = sum(1 for item in dimensions if item.outcome == PairwiseOutcome.CANDIDATE)
    baseline = sum(1 for item in dimensions if item.outcome == PairwiseOutcome.BASELINE)
    if candidate > baseline:
        return PairwiseOutcome.CANDIDATE
    if baseline > candidate:
        return PairwiseOutcome.BASELINE
    if any(item.outcome == PairwiseOutcome.UNCERTAIN for item in dimensions):
        return PairwiseOutcome.UNCERTAIN
    return PairwiseOutcome.EQUIVALENT


def _winner_to_outcome(winner: object) -> PairwiseOutcome:
    name = getattr(winner, "name", winner)
    normalized = str(name or "").strip().lower()
    if normalized == CANDIDATE_CONTESTANT:
        return PairwiseOutcome.CANDIDATE
    if normalized == BASELINE_CONTESTANT:
        return PairwiseOutcome.BASELINE
    return PairwiseOutcome.UNCERTAIN


def _pairwise_criteria(dimension: PairwiseDimension) -> str:
    labels = {
        PairwiseDimension.CLARITY: "clearer and easier for an AI agent to follow accurately",
        PairwiseDimension.AMBIGUITY: "less ambiguous, with fewer plausible unintended interpretations",
        PairwiseDimension.SCOPE_PRECISION: "more precise about scope, applicability, and boundaries",
        PairwiseDimension.INSTRUCTION_HIERARCHY: (
            "clearer about instruction priority, hierarchy, defaults, and exceptions"
        ),
        PairwiseDimension.ACTIONABILITY: "more directly actionable for an AI agent performing repository work",
        PairwiseDimension.SEMANTIC_REQUIREMENT_PRESERVATION: (
            "better at preserving the baseline's required and forbidden behavior"
        ),
        PairwiseDimension.CONFLICTING_INTERPRETATION_RISK: "less likely to support conflicting interpretations",
    }
    return (
        "Choose which documentation variant is predicted to be "
        f"{labels[dimension]}. Treat this as a B-tier predictive semantic judgment, "
        "not measured task success and not empirical Claude/Codex performance. "
        "Prefer uncertainty when the evidence is thin or mixed."
    )


def _pairwise_input(suite: EvaluationSuite) -> str:
    tasks = [scenario.task for scenario in suite.scenarios if scenario.task]
    return "\n".join(tasks) or "Compare documentation for predicted instruction-following quality."


def _pairwise_expected(suite: EvaluationSuite) -> str:
    expected: list[str] = []
    for scenario in suite.scenarios:
        expected.extend(f"Required: {item}" for item in scenario.expected_required)
        expected.extend(f"Forbidden: {item}" for item in scenario.expected_forbidden)
    return "\n".join(expected)


def _snapshot_text(snapshot: DocumentationSnapshot) -> str:
    return "\n\n".join(document.text for document in snapshot.documents)
