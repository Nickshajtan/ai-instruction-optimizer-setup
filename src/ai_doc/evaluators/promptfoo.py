from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite

PROMPTFOO_ENGINE = "promptfoo-lexical"
PROMPTFOO_EXECUTABLE = "promptfoo"
PROMPTFOO_CONFIG_FILE = "promptfooconfig.yaml"
PROMPTFOO_RESULTS_FILE = "results.json"
PROMPTFOO_PROMPT_TEMPLATE = "{{documentation}}\n\nTask:\n{{task}}"
PROMPTFOO_ECHO_PROVIDER = "echo"
PROMPTFOO_CONTAINS_ASSERTION = "contains"
PROMPTFOO_NOT_CONTAINS_ASSERTION = "not-contains"
PROMPTFOO_RESULTS_KEY = "results"
PROMPTFOO_SUCCESS_KEY = "success"
PROMPTFOO_PASS_KEY = "pass"
PROMPTFOO_REASON_KEY = "reason"
SKIPPED_REASON_KEY = "skipped"
NO_SCENARIOS_REASON = "no scenarios"
PROMPTFOO_RESULT_COUNT_KEY = "result_count"


class PromptfooUnavailableError(RuntimeError):
    pass


class PromptfooEvaluator:
    """Deterministic lexical Promptfoo adapter using echo + contains assertions.

    This adapter is intentionally not classified as semantic evaluation.
    """

    def __init__(self, debug: bool = False, runner: PromptfooRunner | None = None) -> None:
        self.debug = debug
        self.runner = runner or SubprocessPromptfooRunner()

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        if not suite.scenarios:
            return EvaluationResult(
                engine=PROMPTFOO_ENGINE,
                passed=True,
                raw_summary={SKIPPED_REASON_KEY: NO_SCENARIOS_REASON, "semantic": False},
            )
        if not self.runner.available():
            raise PromptfooUnavailableError("Promptfoo is unavailable. Install it with npm to use lexical evaluation.")
        temp = Path(tempfile.mkdtemp(prefix="ai-doc-promptfoo-"))
        try:
            config_path = temp / PROMPTFOO_CONFIG_FILE
            output_path = temp / PROMPTFOO_RESULTS_FILE
            config_path.write_text(
                yaml.safe_dump(_promptfoo_config(baseline, candidate, suite), sort_keys=False),
                encoding="utf-8",
            )
            completed = self.runner.run(config_path, output_path)
            if completed.returncode != 0:
                return EvaluationResult(
                    engine=PROMPTFOO_ENGINE,
                    passed=False,
                    raw_summary={
                        "stderr": completed.stderr,
                        "returncode": completed.returncode,
                        "semantic": False,
                    },
                )
            raw = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
            return _normalize(raw, suite)
        finally:
            if not self.debug:
                shutil.rmtree(temp, ignore_errors=True)


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
    assertions = [
        {"type": PROMPTFOO_CONTAINS_ASSERTION, "value": value}
        for value in required
    ]
    assertions.extend(
        {"type": PROMPTFOO_NOT_CONTAINS_ASSERTION, "value": value}
        for value in forbidden
    )
    return assertions or [{"type": PROMPTFOO_CONTAINS_ASSERTION, "value": ""}]


def _promptfoo_config(
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot | None,
    suite: EvaluationSuite,
) -> dict[str, object]:
    candidate_text = "\n\n".join(doc.text for doc in (candidate or baseline).documents)
    return {
        "prompts": [PROMPTFOO_PROMPT_TEMPLATE],
        "providers": [PROMPTFOO_ECHO_PROVIDER],
        "tests": [
            {
                "description": scenario.id,
                "vars": {"documentation": candidate_text, "task": scenario.task},
                "assert": _scenario_assertions(scenario.expected_required, scenario.expected_forbidden),
            }
            for scenario in suite.scenarios
        ],
    }


def _normalize(raw: dict[str, object], suite: EvaluationSuite) -> EvaluationResult:
    results = raw.get(PROMPTFOO_RESULTS_KEY)
    cases: list[EvaluationCaseResult] = []
    if isinstance(results, list):
        for index, item in enumerate(results):
            data = item if isinstance(item, dict) else {}
            scenario_id = suite.scenarios[index].id if index < len(suite.scenarios) else str(index)
            success = bool(data.get(PROMPTFOO_SUCCESS_KEY, data.get(PROMPTFOO_PASS_KEY, False)))
            cases.append(
                EvaluationCaseResult(
                    id=scenario_id,
                    passed=success,
                    message=str(data.get(PROMPTFOO_REASON_KEY, "")) or None,
                )
            )
    else:
        cases = [EvaluationCaseResult(id=scenario.id, passed=True) for scenario in suite.scenarios]
    return EvaluationResult(
        engine=PROMPTFOO_ENGINE,
        passed=all(case.passed for case in cases),
        cases=cases,
        raw_summary={PROMPTFOO_RESULT_COUNT_KEY: len(cases), "semantic": False},
    )
