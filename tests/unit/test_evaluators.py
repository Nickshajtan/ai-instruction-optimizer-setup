from __future__ import annotations

import pytest

import ai_doc.evaluators.deepeval as deepeval_module
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationSuite, PairwiseDimension, PairwiseOutcome
from ai_doc.evaluators.deepeval import DeepEvalEvaluator, DeepEvalUnavailableError
from ai_doc.evaluators.promptfoo import (
    PROMPTFOO_CONTAINS_ASSERTION,
    PROMPTFOO_ENGINE,
    PROMPTFOO_NOT_CONTAINS_ASSERTION,
    PROMPTFOO_PROMPT_TEMPLATE,
    _normalize,
    _promptfoo_config,
)
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.optimizer.semantic import normalize_pairwise_response


def _snapshot(text: str) -> DocumentationSnapshot:
    return DocumentationSnapshot.model_validate(
        {
            "root": ".",
            "documents": [
                {
                    "path": "AGENTS.md",
                    "relative_path": "AGENTS.md",
                    "profile": "instruction",
                    "text": text,
                    "token_count": 4,
                }
            ],
        }
    )


def test_promptfoo_config_isolates_assertions_per_scenario() -> None:
    suite = EvaluationSuite.model_validate(
        {
            "scenarios": [
                {
                    "id": "setup",
                    "task": "Install the tool.",
                    "expected_required": ["run setup"],
                    "expected_forbidden": ["skip validation"],
                },
                {"id": "review", "task": "Review a change.", "expected_required": ["inspect diff"]},
            ]
        }
    )

    config = _promptfoo_config(_snapshot("Docs"), None, suite)

    assert config["prompts"] == [PROMPTFOO_PROMPT_TEMPLATE]
    assert config["providers"] == ["echo"]
    assert config["tests"][0]["description"] == "setup"
    assert config["tests"][0]["vars"] == {"documentation": "Docs", "task": "Install the tool."}
    assert config["tests"][0]["assert"] == [
        {"type": PROMPTFOO_CONTAINS_ASSERTION, "value": "run setup"},
        {"type": PROMPTFOO_NOT_CONTAINS_ASSERTION, "value": "skip validation"},
    ]
    assert config["tests"][1]["description"] == "review"
    assert config["tests"][1]["vars"] == {"documentation": "Docs", "task": "Review a change."}
    assert config["tests"][1]["assert"] == [{"type": PROMPTFOO_CONTAINS_ASSERTION, "value": "inspect diff"}]


def test_promptfoo_config_keeps_valid_default_assertion_for_unconstrained_scenario() -> None:
    suite = EvaluationSuite.model_validate({"scenarios": [{"id": "smoke", "task": "Read the docs."}]})

    config = _promptfoo_config(_snapshot("Docs"), None, suite)

    assert config["tests"][0]["assert"] == [{"type": PROMPTFOO_CONTAINS_ASSERTION, "value": ""}]


def test_promptfoo_normalize_accepts_success_and_pass_keys() -> None:
    suite = EvaluationSuite.model_validate({"scenarios": [{"id": "one", "task": ""}, {"id": "two", "task": ""}]})
    result = _normalize({"results": [{"success": True}, {"pass": False, "reason": "missing route"}]}, suite)
    assert result.engine == PROMPTFOO_ENGINE
    assert result.passed is False
    assert [case.passed for case in result.cases] == [True, False]
    assert result.cases[1].message == "missing route"
    assert result.raw_summary["semantic"] is False


def test_load_evaluation_suite_reads_yaml_keys(tmp_path) -> None:
    eval_dir = tmp_path / ".ai-doc" / "evals"
    eval_dir.mkdir(parents=True)
    (eval_dir / "basic.yaml").write_text(
        """
id: setup
profile: coding
task: Install the tool.
expected:
  required: [run setup]
  forbidden: [skip validation]
tags: [smoke]
""",
        encoding="utf-8",
    )
    suite = load_evaluation_suite(tmp_path)
    assert suite.scenarios[0].id == "setup"
    assert suite.scenarios[0].expected_required == ["run setup"]
    assert suite.scenarios[0].expected_forbidden == ["skip validation"]
    assert suite.scenarios[0].tags == ["smoke"]


def test_deepeval_symbol_loader_wraps_missing_dependency(monkeypatch) -> None:
    def missing_import(name: str) -> object:
        raise ImportError(name)

    monkeypatch.setattr(deepeval_module, "import_module", missing_import)
    with pytest.raises(DeepEvalUnavailableError):
        deepeval_module._load_deepeval_symbols()


def test_deepeval_evaluator_uses_baseline_when_candidate_absent(monkeypatch) -> None:
    measured: list[object] = []

    class FakeMetric:
        score = 0.8
        reason = "ok"

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def measure(self, test_case: object) -> None:
            measured.append(test_case)

        def is_successful(self) -> bool:
            return True

    class FakeTestCase:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        deepeval_module,
        "_load_deepeval_symbols",
        lambda: deepeval_module.DeepEvalSymbols(
            geval=FakeMetric,
            llm_test_case=FakeTestCase,
            actual_output_param=object(),
            expected_output_param=object(),
            input_param=object(),
        ),
    )
    suite = EvaluationSuite.model_validate(
        {"scenarios": [{"id": "setup", "task": "Install.", "expected_required": ["run setup"]}]}
    )

    result = DeepEvalEvaluator().evaluate(_snapshot("BASELINE CONTENT run setup"), None, suite)

    assert result.engine == "deepeval"
    assert result.passed is True
    assert result.cases[0].score == 0.8
    assert result.raw_summary["semantic"] is True
    assert measured
    assert "BASELINE CONTENT" in measured[0].kwargs["actual_output"]


def test_pairwise_response_normalizes_all_outcomes_and_dimensions() -> None:
    result = normalize_pairwise_response(
        {
            "overall": "candidate_better",
            "dimensions": [
                {"dimension": "clarity", "outcome": "candidate_wins", "evidence": "clearer"},
                {"dimension": "ambiguity", "outcome": "baseline_wins", "evidence": "less vague"},
                {"dimension": "scope_precision", "outcome": "tie", "evidence": "same scope"},
                {"dimension": "instruction_hierarchy", "outcome": "unclear", "evidence": "mixed"},
            ],
        },
        engine="test",
    )

    assert result.overall == PairwiseOutcome.CANDIDATE
    by_dimension = {item.dimension: item for item in result.dimensions}
    assert set(by_dimension) == set(PairwiseDimension)
    assert by_dimension[PairwiseDimension.CLARITY].outcome == PairwiseOutcome.CANDIDATE
    assert by_dimension[PairwiseDimension.AMBIGUITY].outcome == PairwiseOutcome.BASELINE
    assert by_dimension[PairwiseDimension.SCOPE_PRECISION].outcome == PairwiseOutcome.EQUIVALENT
    assert by_dimension[PairwiseDimension.INSTRUCTION_HIERARCHY].outcome == PairwiseOutcome.UNCERTAIN
    assert by_dimension[PairwiseDimension.ACTIONABILITY].outcome == PairwiseOutcome.UNCERTAIN


def test_deepeval_pairwise_uses_arena_geval_when_available(monkeypatch) -> None:
    measured: list[object] = []

    class FakeArenaMetric:
        winner = "candidate"
        reason = "candidate has clearer instructions"

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def measure(self, test_case: object) -> None:
            measured.append(test_case)

    class FakeTestCase:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeContestant:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        deepeval_module,
        "_load_deepeval_symbols",
        lambda: deepeval_module.DeepEvalSymbols(
            geval=object,
            llm_test_case=FakeTestCase,
            actual_output_param=object(),
            expected_output_param=object(),
            input_param=object(),
            arena_geval=FakeArenaMetric,
            arena_test_case=FakeTestCase,
            contestant=FakeContestant,
        ),
    )

    result = DeepEvalEvaluator().compare_pairwise(
        _snapshot("baseline"),
        _snapshot("candidate"),
        EvaluationSuite.model_validate({"scenarios": [{"id": "one", "task": "Do work."}]}),
    )

    assert result.engine == "deepeval-arena-geval"
    assert result.overall == PairwiseOutcome.CANDIDATE
    assert len(result.dimensions) == len(PairwiseDimension)
    assert measured
