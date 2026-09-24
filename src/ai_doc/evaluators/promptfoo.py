from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.providers.semantic import ProviderUsage

PROMPTFOO_ENGINE = "promptfoo-lexical"
PROMPTFOO_MODEL_GRADED_ENGINE = "promptfoo-model-graded"
PROMPTFOO_EXECUTABLE = "promptfoo"
PROMPTFOO_CONFIG_FILE = "promptfooconfig.yaml"
PROMPTFOO_RESULTS_FILE = "results.json"
PROMPTFOO_PROMPT_TEMPLATE = "{{documentation}}\n\nTask:\n{{task}}"
PROMPTFOO_ECHO_PROVIDER = "echo"
PROMPTFOO_MODE_LEXICAL = "lexical"
PROMPTFOO_MODE_MODEL_GRADED = "model_graded"
PROMPTFOO_BACKEND = "promptfoo"
PROMPTFOO_CONTAINS_ASSERTION = "contains"
PROMPTFOO_NOT_CONTAINS_ASSERTION = "not-contains"
PROMPTFOO_LLM_RUBRIC_ASSERTION = "llm-rubric"
PROMPTFOO_RESULTS_KEY = "results"
PROMPTFOO_SUCCESS_KEY = "success"
PROMPTFOO_PASS_KEY = "pass"
PROMPTFOO_REASON_KEY = "reason"
SKIPPED_REASON_KEY = "skipped"
NO_SCENARIOS_REASON = "no scenarios"
PROMPTFOO_RESULT_COUNT_KEY = "result_count"
PROMPTFOO_GRADING_RESULT_KEY = "gradingResult"
PROMPTFOO_ADAPTER_ERROR_CASE_ID = "promptfoo-output"
PROMPTFOO_UNSUPPORTED_RESULTS_MESSAGE = "Promptfoo returned unsupported results JSON."
PROMPTFOO_EXPLICIT_MODEL_MESSAGE = (
    "Promptfoo model-graded evaluation requires an explicitly configured model. "
    "No implicit provider or model will be selected."
)
PROMPTFOO_UNSUPPORTED_MODE_MESSAGE = "Unsupported Promptfoo evaluation mode"
PROMPTFOO_UNSUPPORTED_ASSERTION_MESSAGE = "Unsupported Promptfoo model-graded assertion"
PROMPTFOO_UNKNOWN_USAGE_FIELDS = ["input_tokens", "output_tokens", "cost_usd"]


class PromptfooUnavailableError(RuntimeError):
    pass


class PromptfooConfigurationError(RuntimeError):
    pass


class PromptfooEvaluator:
    """Promptfoo adapter for lexical and explicit model-graded assertions.

    Lexical mode remains deterministic echo/contains evidence. Model-graded mode
    delegates semantic grading to Promptfoo instead of reimplementing it here.
    """

    def __init__(
        self,
        debug: bool = False,
        runner: PromptfooRunner | None = None,
        *,
        mode: str = PROMPTFOO_MODE_LEXICAL,
        model: str | None = None,
        assertion: str | None = None,
    ) -> None:
        self.debug = debug
        self.runner = runner or SubprocessPromptfooRunner()
        self.mode = mode
        self.model = model
        self.assertion = assertion or PROMPTFOO_LLM_RUBRIC_ASSERTION
        self.last_usage = ProviderUsage(requests=0, cost_source="unknown")

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        self._validate()
        if not suite.scenarios:
            return EvaluationResult(
                engine=self._engine,
                passed=True,
                raw_summary={
                    SKIPPED_REASON_KEY: NO_SCENARIOS_REASON,
                    **self._summary_metadata(0),
                },
            )
        if not self.runner.available():
            raise PromptfooUnavailableError("Promptfoo is unavailable. Install it with npm to use evaluation.")
        temp = Path(tempfile.mkdtemp(prefix="ai-doc-promptfoo-"))
        try:
            config_path = temp / PROMPTFOO_CONFIG_FILE
            output_path = temp / PROMPTFOO_RESULTS_FILE
            config_path.write_text(
                yaml.safe_dump(
                    _promptfoo_config(
                        baseline,
                        candidate,
                        suite,
                        mode=self.mode,
                        model=self.model,
                        assertion=self.assertion,
                    ),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            completed = self.runner.run(config_path, output_path)
            self.last_usage = ProviderUsage(requests=1, cost_source="unknown")
            if completed.returncode != 0:
                return EvaluationResult(
                    engine=self._engine,
                    passed=False,
                    raw_summary={
                        "stderr": completed.stderr,
                        "returncode": completed.returncode,
                        **self._summary_metadata(1),
                    },
                )
            raw = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
            return _normalize(raw, suite, mode=self.mode, assertion=self.assertion)
        finally:
            if not self.debug:
                shutil.rmtree(temp, ignore_errors=True)

    def drain_usage(self) -> ProviderUsage:
        usage = self.last_usage
        self.last_usage = ProviderUsage(requests=0, cost_source="unknown")
        return usage

    @property
    def _engine(self) -> str:
        return PROMPTFOO_MODEL_GRADED_ENGINE if self.mode == PROMPTFOO_MODE_MODEL_GRADED else PROMPTFOO_ENGINE

    def _validate(self) -> None:
        if self.mode not in {PROMPTFOO_MODE_LEXICAL, PROMPTFOO_MODE_MODEL_GRADED}:
            raise PromptfooConfigurationError(f"{PROMPTFOO_UNSUPPORTED_MODE_MESSAGE}: {self.mode}")
        if self.mode == PROMPTFOO_MODE_LEXICAL:
            return
        if not self.model:
            raise PromptfooConfigurationError(PROMPTFOO_EXPLICIT_MODEL_MESSAGE)
        if self.assertion != PROMPTFOO_LLM_RUBRIC_ASSERTION:
            raise PromptfooConfigurationError(
                f"{PROMPTFOO_UNSUPPORTED_ASSERTION_MESSAGE}: {self.assertion}. "
                f"Supported value: {PROMPTFOO_LLM_RUBRIC_ASSERTION}."
            )

    def _summary_metadata(self, requests: int) -> dict[str, object]:
        return _summary_metadata(self.mode, self.assertion, requests)


class PromptfooRunner:
    def available(self) -> bool:
        raise NotImplementedError

    def run(self, config_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
        raise NotImplementedError


class SubprocessPromptfooRunner(PromptfooRunner):
    def available(self) -> bool:
        return shutil.which(PROMPTFOO_EXECUTABLE) is not None

    def run(self, config_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PROMPTFOO_EXECUTABLE, "eval", "-c", str(config_path), "--output", str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )


def _scenario_assertions(required: list[str], forbidden: list[str]) -> list[dict[str, str]]:
    assertions = [{"type": PROMPTFOO_CONTAINS_ASSERTION, "value": value} for value in required]
    assertions.extend({"type": PROMPTFOO_NOT_CONTAINS_ASSERTION, "value": value} for value in forbidden)
    return assertions or [{"type": PROMPTFOO_CONTAINS_ASSERTION, "value": ""}]


def _scenario_rubric(required: list[str], forbidden: list[str]) -> str:
    lines = [
        "Evaluate whether the supplied documentation supports the task.",
        "This is B-tier predictive semantic evidence, not observed target-agent execution.",
    ]
    if required:
        lines.append("Required behavior:")
        lines.extend(f"- {item}" for item in required)
    if forbidden:
        lines.append("Forbidden behavior:")
        lines.extend(f"- {item}" for item in forbidden)
    if not required and not forbidden:
        lines.append("Pass if the documentation is relevant and not misleading for the task.")
    return "\n".join(lines)


def _model_graded_assertions(
    required: list[str],
    forbidden: list[str],
    assertion: str | None,
    model: str,
) -> list[dict[str, str]]:
    assertion_type = assertion or PROMPTFOO_LLM_RUBRIC_ASSERTION
    return [{"type": assertion_type, "provider": model, "value": _scenario_rubric(required, forbidden)}]


def _promptfoo_config(
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot | None,
    suite: EvaluationSuite,
    *,
    mode: str = PROMPTFOO_MODE_LEXICAL,
    model: str | None = None,
    assertion: str | None = None,
) -> dict[str, object]:
    candidate_text = "\n\n".join(doc.text for doc in (candidate or baseline).documents)
    return {
        "prompts": [PROMPTFOO_PROMPT_TEMPLATE],
        "providers": [PROMPTFOO_ECHO_PROVIDER],
        "tests": [
            {
                "description": scenario.id,
                "vars": {"documentation": candidate_text, "task": scenario.task},
                "assert": (
                    _model_graded_assertions(
                        scenario.expected_required,
                        scenario.expected_forbidden,
                        assertion,
                        model or "",
                    )
                    if mode == PROMPTFOO_MODE_MODEL_GRADED
                    else _scenario_assertions(scenario.expected_required, scenario.expected_forbidden)
                ),
            }
            for scenario in suite.scenarios
        ],
    }


def _normalize(
    raw: dict[str, object],
    suite: EvaluationSuite,
    *,
    mode: str = PROMPTFOO_MODE_LEXICAL,
    assertion: str | None = None,
) -> EvaluationResult:
    results = _promptfoo_result_rows(raw)
    if results is None:
        return EvaluationResult(
            engine=PROMPTFOO_MODEL_GRADED_ENGINE if mode == PROMPTFOO_MODE_MODEL_GRADED else PROMPTFOO_ENGINE,
            passed=False,
            cases=[
                EvaluationCaseResult(
                    id=PROMPTFOO_ADAPTER_ERROR_CASE_ID,
                    passed=False,
                    message=PROMPTFOO_UNSUPPORTED_RESULTS_MESSAGE,
                )
            ],
            raw_summary={
                PROMPTFOO_RESULT_COUNT_KEY: 0,
                "adapter_error": PROMPTFOO_UNSUPPORTED_RESULTS_MESSAGE,
                **_summary_metadata(mode, assertion, 1),
            },
        )
    cases = []
    for index, item in enumerate(results):
        data = item if isinstance(item, dict) else {}
        scenario_id = suite.scenarios[index].id if index < len(suite.scenarios) else str(index)
        cases.append(
            EvaluationCaseResult(
                id=scenario_id,
                passed=_case_passed(data),
                score=_case_score(data),
                message=_case_reason(data),
            )
        )
    return EvaluationResult(
        engine=PROMPTFOO_MODEL_GRADED_ENGINE if mode == PROMPTFOO_MODE_MODEL_GRADED else PROMPTFOO_ENGINE,
        passed=all(case.passed for case in cases),
        cases=cases,
        raw_summary={PROMPTFOO_RESULT_COUNT_KEY: len(cases), **_summary_metadata(mode, assertion, 1)},
    )


def _promptfoo_result_rows(raw: dict[str, object]) -> list[object] | None:
    results = raw.get(PROMPTFOO_RESULTS_KEY)
    if isinstance(results, list):
        return results
    if isinstance(results, dict):
        nested = results.get(PROMPTFOO_RESULTS_KEY)
        if isinstance(nested, list):
            return nested
    return None


def _case_passed(data: dict[str, object]) -> bool:
    grading = data.get(PROMPTFOO_GRADING_RESULT_KEY)
    if isinstance(data.get(PROMPTFOO_SUCCESS_KEY), bool):
        return bool(data[PROMPTFOO_SUCCESS_KEY])
    if isinstance(data.get(PROMPTFOO_PASS_KEY), bool):
        return bool(data[PROMPTFOO_PASS_KEY])
    if isinstance(grading, dict) and isinstance(grading.get(PROMPTFOO_PASS_KEY), bool):
        return bool(grading[PROMPTFOO_PASS_KEY])
    return False


def _case_score(data: dict[str, object]) -> float | None:
    grading = data.get(PROMPTFOO_GRADING_RESULT_KEY)
    value = grading.get("score") if isinstance(grading, dict) else data.get("score")
    if isinstance(value, int | float):
        return float(value)
    return None


def _case_reason(data: dict[str, object]) -> str | None:
    grading = data.get(PROMPTFOO_GRADING_RESULT_KEY)
    values = [data.get(PROMPTFOO_REASON_KEY)]
    if isinstance(grading, dict):
        values.extend([grading.get(PROMPTFOO_REASON_KEY), grading.get("comment")])
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    if not _case_passed(data):
        return "Promptfoo result did not include a passing status."
    return None


def _summary_metadata(mode: str, assertion: str | None, requests: int) -> dict[str, object]:
    semantic = mode == PROMPTFOO_MODE_MODEL_GRADED
    summary: dict[str, object] = {
        "semantic": semantic,
        "backend": PROMPTFOO_BACKEND,
        "mode": mode,
        "usage": ProviderUsage(requests=requests, cost_source="unknown").model_dump(mode="json"),
        "usage_unknown": PROMPTFOO_UNKNOWN_USAGE_FIELDS,
    }
    if semantic:
        summary["assertion"] = assertion or PROMPTFOO_LLM_RUBRIC_ASSERTION
    return summary
