from __future__ import annotations

import re
from typing import Protocol

from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationScenario, EvaluationSuite, Evaluator

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
ALWAYS_LOADED_PROFILES = {DocumentProfile.INSTRUCTION, DocumentProfile.SKILL}


class ContextSelector(Protocol):
    def select(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> DocumentationSnapshot: ...


class DeterministicContextSelector:
    """Approximate agent context loading without pretending the whole corpus is always loaded."""

    def select(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> DocumentationSnapshot:
        always = [document for document in snapshot.documents if document.profile in ALWAYS_LOADED_PROFILES]
        selected_paths = {document.relative_path for document in always}
        task_terms = _terms(scenario.task)
        by_path = snapshot.by_relative_path()

        for document in snapshot.documents:
            if document.relative_path in selected_paths:
                continue
            searchable = f"{document.relative_path} {' '.join(heading.title for heading in document.headings)}"
            if task_terms & _terms(searchable):
                selected_paths.add(document.relative_path)

        for document in always:
            for link in document.links:
                target = link.resolved_path or link.target.split("#", 1)[0]
                if target in by_path and (_terms(link.label) & task_terms or _terms(document.text) & task_terms):
                    selected_paths.add(target)

        selected = tuple(document for document in snapshot.documents if document.relative_path in selected_paths)
        return DocumentationSnapshot(root=snapshot.root, documents=selected)


class ScenarioContextEvaluator:
    """Run an evaluator independently per scenario against task-selected context."""

    def __init__(self, evaluator: Evaluator, selector: ContextSelector | None = None) -> None:
        self.evaluator = evaluator
        self.selector = selector or DeterministicContextSelector()

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        cases: list[EvaluationCaseResult] = []
        engines: set[str] = set()
        context_paths: dict[str, list[str]] = {}
        semantic = True
        for scenario in suite.scenarios:
            selected_baseline = self.selector.select(baseline, scenario)
            selected_candidate = self.selector.select(candidate, scenario) if candidate is not None else None
            effective = selected_candidate or selected_baseline
            context_paths[scenario.id] = [document.relative_path for document in effective.documents]
            result = self.evaluator.evaluate(
                selected_baseline,
                selected_candidate,
                EvaluationSuite(scenarios=[scenario]),
            )
            engines.add(result.engine)
            semantic = semantic and bool(result.raw_summary.get("semantic", True))
            if result.cases:
                cases.extend(result.cases)
            else:
                cases.append(EvaluationCaseResult(id=scenario.id, passed=result.passed))
        return EvaluationResult(
            engine="+".join(sorted(engines)) or "none",
            passed=all(case.passed for case in cases),
            cases=cases,
            raw_summary={"semantic": semantic, "effective_context": context_paths},
        )


def _terms(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}
