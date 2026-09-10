from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.evaluators.context import DeterministicContextSelector, ScenarioContextEvaluator


def _snapshot() -> DocumentationSnapshot:
    return DocumentationSnapshot.model_validate(
        {
            "root": ".",
            "documents": [
                {"path": "AGENTS.md", "relative_path": "AGENTS.md", "profile": "instruction",
                 "text": "For database migrations read docs/database.md.", "token_count": 8},
                {"path": "docs/database.md", "relative_path": "docs/database.md", "profile": "reference",
                 "text": "Database migration procedure.", "token_count": 4},
                {"path": "docs/css.md", "relative_path": "docs/css.md", "profile": "reference",
                 "text": "CSS conventions.", "token_count": 2},
            ],
        }
    )


def test_selector_distinguishes_always_loaded_and_explicitly_routed_context() -> None:
    suite = EvaluationSuite.model_validate({"scenarios": [{"id": "db", "task": "Change a database migration"}]})
    selected = DeterministicContextSelector().select(_snapshot(), suite.scenarios[0])
    paths = {document.relative_path for document in selected.documents}
    assert paths == {"AGENTS.md", "docs/database.md"}
    assert selected.total_tokens < _snapshot().total_tokens


def test_scenario_context_evaluator_does_not_invent_unrouted_context() -> None:
    seen: list[tuple[str, set[str]]] = []

    class FakeSemanticEvaluator:
        def evaluate(self, baseline, candidate, suite):
            snapshot = candidate or baseline
            scenario = suite.scenarios[0]
            seen.append((scenario.id, {document.relative_path for document in snapshot.documents}))
            return EvaluationResult(engine="fake-semantic", passed=True,
                cases=[EvaluationCaseResult(id=scenario.id, passed=True, score=1.0)], raw_summary={"semantic": True})

    suite = EvaluationSuite.model_validate({"scenarios": [
        {"id": "db", "task": "Change a database migration"}, {"id": "css", "task": "Change CSS conventions"}]})
    result = ScenarioContextEvaluator(FakeSemanticEvaluator()).evaluate(_snapshot(), None, suite)
    assert result.passed is True
    assert seen[0][1] == {"AGENTS.md", "docs/database.md"}
    assert seen[1][1] == {"AGENTS.md"}
    assert result.raw_summary["effective_context"]["db"] == ["AGENTS.md", "docs/database.md"]
    assert result.raw_summary["effective_context"]["css"] == ["AGENTS.md"]
