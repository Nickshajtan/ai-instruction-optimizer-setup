from __future__ import annotations

from typing import cast

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.domain.optimization import OptimizationFeedback, SearchMemory
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.invariants import Invariant, InvariantImportance, InvariantSemanticStatus
from ai_doc.providers.semantic import ProviderUsage, SemanticProvider


class ProviderSemanticCandidateGenerator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)

    def generate(self, snapshot: DocumentationSnapshot, invariants: list[Invariant], strategy: GenerationStrategyName,
                 previous_summaries: list[str], explored_transformations: list[str],
                 feedback: OptimizationFeedback | None, memory: SearchMemory) -> tuple[CandidateProposal, dict[str, str]]:
        response = self.provider.invoke("generate_candidate", {
            "strategy": strategy.value, "documents": {d.relative_path: d.text for d in snapshot.documents},
            "invariants": [item.model_dump(mode="json") for item in invariants], "previous_summaries": previous_summaries,
            "explored_transformations": explored_transformations,
            "feedback": feedback.model_dump(mode="json") if feedback else None,
            "search_memory": memory.model_dump(mode="json"),
        })
        self.last_usage = response.usage
        return CandidateProposal.model_validate(response.data.get("proposal")), cast(dict[str, str], response.data.get("documents", {}))


class ProviderSemanticInvariantService:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)
        self.usage_history: list[ProviderUsage] = []

    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]:
        response = self.provider.invoke("discover_invariants", {"documents": {d.relative_path: d.text for d in snapshot.documents}})
        self.last_usage = response.usage
        self.usage_history.append(response.usage)
        discovered: list[Invariant] = []
        for raw in cast(list[dict[str, object]], response.data.get("invariants", [])):
            invariant = Invariant.model_validate(raw)
            if invariant.importance == InvariantImportance.CRITICAL and invariant.confidence >= 0.8:
                discovered.append(invariant)
        return discovered

    def verify(self, invariant: Invariant, candidate: DocumentationSnapshot) -> InvariantSemanticStatus:
        response = self.provider.invoke("verify_invariant", {
            "invariant": invariant.model_dump(mode="json"), "documents": {d.relative_path: d.text for d in candidate.documents},
            "statuses": [status.value for status in InvariantSemanticStatus],
        })
        self.last_usage = response.usage
        self.usage_history.append(response.usage)
        return InvariantSemanticStatus(str(response.data.get("status", "uncertain")))


class ProviderSemanticEvaluator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)

    def evaluate(self, baseline: DocumentationSnapshot, candidate: DocumentationSnapshot | None,
                 suite: EvaluationSuite) -> EvaluationResult:
        effective = candidate or baseline
        response = self.provider.invoke("evaluate", {
            "documents": {d.relative_path: d.text for d in effective.documents},
            "scenarios": [scenario.model_dump(mode="json") for scenario in suite.scenarios],
        })
        self.last_usage = response.usage
        cases = [EvaluationCaseResult.model_validate(item) for item in cast(list[dict[str, object]], response.data.get("cases", []))]
        return EvaluationResult(engine="semantic-provider", passed=all(case.passed for case in cases), cases=cases,
                                raw_summary={"semantic": True, "usage": response.usage.model_dump(mode="json")})
