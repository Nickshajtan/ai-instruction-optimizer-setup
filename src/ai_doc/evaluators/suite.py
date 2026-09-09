from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite

EVALUATION_DIRECTORY = ".ai-doc/evals"
EVALUATION_FILE_PATTERN = "*.y*ml"
DEFAULT_SCENARIO_PROFILE = "generic"
EXPECTED_KEY = "expected"
EXPECTED_REQUIRED_KEY = "required"
EXPECTED_FORBIDDEN_KEY = "forbidden"
SCENARIO_ID_KEY = "id"
SCENARIO_PROFILE_KEY = "profile"
SCENARIO_TASK_KEY = "task"
SCENARIO_TAGS_KEY = "tags"


def load_evaluation_suite(root: Path) -> EvaluationSuite:
    eval_dir = root / EVALUATION_DIRECTORY
    if not eval_dir.exists():
        return EvaluationSuite()
    scenarios: list[EvaluationScenario] = []
    for path in sorted(eval_dir.glob(EVALUATION_FILE_PATTERN)):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        scenarios.append(_scenario_from_yaml(data))
    return EvaluationSuite(scenarios=scenarios)


def _scenario_from_yaml(data: dict[str, Any]) -> EvaluationScenario:
    expected = data.get(EXPECTED_KEY) or {}
    return EvaluationScenario(
        id=str(data[SCENARIO_ID_KEY]),
        profile=str(data.get(SCENARIO_PROFILE_KEY, DEFAULT_SCENARIO_PROFILE)),
        task=str(data.get(SCENARIO_TASK_KEY, "")),
        expected_required=list(expected.get(EXPECTED_REQUIRED_KEY) or []),
        expected_forbidden=list(expected.get(EXPECTED_FORBIDDEN_KEY) or []),
        tags=list(data.get(SCENARIO_TAGS_KEY) or []),
    )
