from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite

DEEPEVAL_ENGINE = "deepeval"
DEEPEVAL_METRIC_PREFIX = "ai-doc"
DEEPEVAL_DEFAULT_THRESHOLD = 0.5
DEEPEVAL_CRITERIA = (
    "Evaluate whether the documentation supports the required behavior "
    "without violating forbidden behavior."
)
DEEPEVAL_REASON_ATTRIBUTE = "reason"
DEEPEVAL_SCORE_ATTRIBUTE = "score"


class DeepEvalUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepEvalSymbols:
    geval: Callable[..., Any]
    llm_test_case: Callable[..., Any]
    actual_output_param: object
    expected_output_param: object


class DeepEvalEvaluator:
    """Optional DeepEval adapter.

    The current public API represents single-turn cases with `LLMTestCase` and
    custom semantic judging with `GEval` plus `SingleTurnParams`. Imports stay
    inside this adapter so DeepEval is not a core dependency.
    """

    def __init__(self, threshold: float = DEEPEVAL_DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        del baseline
        symbols = _load_deepeval_symbols()
        documents = candidate.documents if candidate else ()
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
            test_case = symbols.llm_test_case(
                input=scenario.task,
                actual_output=actual,
                expected_output="\n".join(scenario.expected_required),
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
    return DeepEvalSymbols(
        geval=cast(Callable[..., Any], metrics_api.GEval),
        llm_test_case=cast(Callable[..., Any], test_case_api.LLMTestCase),
        actual_output_param=single_turn_params.ACTUAL_OUTPUT,
        expected_output_param=single_turn_params.EXPECTED_OUTPUT,
    )


def _metric_score(metric: object) -> float | None:
    score = getattr(metric, DEEPEVAL_SCORE_ATTRIBUTE, None)
    return float(score) if score is not None else None
