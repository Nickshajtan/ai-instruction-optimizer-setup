from __future__ import annotations

import re
from typing import Protocol

from ai_doc.domain.documents import DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import (
    EvaluationCaseResult,
    EvaluationResult,
    EvaluationScenario,
    EvaluationSuite,
    Evaluator,
)

WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
ROUTER_RE = re.compile(r"\b(read|load|consult|see|follow|use|open|refer)\b", re.IGNORECASE)
ALWAYS_LOADED_PROFILES = {DocumentProfile.INSTRUCTION, DocumentProfile.SKILL}
ROUTER_CONTEXT_LINES = 1


class ContextSelector(Protocol):
    def select(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> DocumentationSnapshot: ...


class DeterministicContextSelector:
    """Approximate reachable agent context; target vocabulary alone never creates reachability."""

    def select(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> DocumentationSnapshot:
        always = [document for document in snapshot.documents if document.profile in ALWAYS_LOADED_PROFILES]
        selected_paths = {document.relative_path for document in always}
        task_terms = _terms(scenario.task)
        by_path = snapshot.by_relative_path()
        queue = list(always)
        while queue:
            document = queue.pop(0)
            lines = document.text.splitlines()
            routed = self._linked_routes(document, lines, task_terms, by_path)
            routed.update(self._plain_text_routes(lines, task_terms, by_path))
            for target in sorted(routed - selected_paths):
                selected_paths.add(target)
                queue.append(by_path[target])
        selected = tuple(document for document in snapshot.documents if document.relative_path in selected_paths)
        return DocumentationSnapshot(root=snapshot.root, documents=selected)

    def _linked_routes(self, document, lines, task_terms, by_path) -> set[str]:
        routed: set[str] = set()
        for link in document.links:
            target = link.resolved_path or link.target.split("#", 1)[0]
            route_text = _link_context(lines, link.line)
            if target in by_path and ROUTER_RE.search(route_text) and task_terms & _terms(f"{link.label} {route_text}"):
                routed.add(target)
        return routed

    def _plain_text_routes(self, lines: list[str], task_terms: set[str], by_path: dict) -> set[str]:
        routed: set[str] = set()
        for line in lines:
            if not ROUTER_RE.search(line) or not (task_terms & _terms(line)):
                continue
            for target in by_path:
                if target in line:
                    routed.add(target)
        return routed


class ScenarioContextEvaluator:
    """Run an evaluator independently per scenario against task-selected reachable context."""

    def __init__(self, evaluator: Evaluator, selector: ContextSelector | None = None) -> None:
        self.evaluator = evaluator
        self.selector = selector or DeterministicContextSelector()

    def evaluate(
        self, baseline: DocumentationSnapshot, candidate: DocumentationSnapshot | None, suite: EvaluationSuite
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
                selected_baseline, selected_candidate, EvaluationSuite(scenarios=[scenario])
            )
            engines.add(result.engine)
            semantic = semantic and bool(result.raw_summary.get("semantic", True))
            cases.extend(result.cases or [EvaluationCaseResult(id=scenario.id, passed=result.passed)])
        return EvaluationResult(
            engine="+".join(sorted(engines)) or "none",
            passed=all(case.passed for case in cases),
            cases=cases,
            raw_summary={"semantic": semantic, "effective_context": context_paths},
        )


def _link_context(lines: list[str], line: int) -> str:
    index = max(line - 1, 0)
    start = max(index - ROUTER_CONTEXT_LINES, 0)
    end = min(index + ROUTER_CONTEXT_LINES + 1, len(lines))
    return " ".join(lines[start:end])


def _terms(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}
