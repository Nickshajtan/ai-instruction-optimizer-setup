from __future__ import annotations

from typing import cast

from ai_doc.config.search import SearchConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult, EvaluationSuite
from ai_doc.domain.optimization import OptimizationFeedback, SearchMemory
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.invariants import Invariant, InvariantImportance, InvariantSemanticStatus
from ai_doc.optimizer.prompt_suboptimizer import PromptArtifact, PromptOptimizationResult
from ai_doc.providers.semantic import ProviderUsage, SemanticProvider


class ProviderSemanticCandidateGenerator:
    def __init__(self, provider: SemanticProvider) -> None: self.provider, self.last_usage = provider, ProviderUsage(requests=0)
    def generate(self, snapshot: DocumentationSnapshot, invariants: list[Invariant], strategy: GenerationStrategyName,
                 previous_summaries: list[str], explored_transformations: list[str], feedback: OptimizationFeedback | None,
                 memory: SearchMemory) -> tuple[CandidateProposal, dict[str, str]]:
        response = self.provider.invoke("generate_candidate", {"strategy": strategy.value,
            "documents": {d.relative_path: d.text for d in snapshot.documents}, "invariants": [i.model_dump(mode="json") for i in invariants],
            "previous_summaries": previous_summaries, "explored_transformations": explored_transformations,
            "feedback": feedback.model_dump(mode="json") if feedback else None, "search_memory": memory.model_dump(mode="json")})
        self.last_usage = response.usage
        return CandidateProposal.model_validate(response.data.get("proposal")), cast(dict[str, str], response.data.get("documents", {}))


class ProviderSemanticInvariantService:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider, self.last_usage, self.usage_history = provider, ProviderUsage(requests=0), []
    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]:
        response = self.provider.invoke("discover_invariants", {"documents": {d.relative_path: d.text for d in snapshot.documents}})
        self.last_usage = response.usage; self.usage_history.append(response.usage)
        result = []
        for raw in cast(list[dict[str, object]], response.data.get("invariants", [])):
            item = Invariant.model_validate(raw)
            if item.importance == InvariantImportance.CRITICAL and item.confidence >= 0.8: result.append(item)
        return result
    def verify(self, invariant: Invariant, candidate: DocumentationSnapshot) -> InvariantSemanticStatus:
        response = self.provider.invoke("verify_invariant", {"invariant": invariant.model_dump(mode="json"),
            "documents": {d.relative_path: d.text for d in candidate.documents}, "statuses": [s.value for s in InvariantSemanticStatus]})
        self.last_usage = response.usage; self.usage_history.append(response.usage)
        return InvariantSemanticStatus(str(response.data.get("status", "uncertain")))


class ProviderSemanticEvaluator:
    def __init__(self, provider: SemanticProvider) -> None: self.provider, self.last_usage = provider, ProviderUsage(requests=0)
    def evaluate(self, baseline: DocumentationSnapshot, candidate: DocumentationSnapshot | None, suite: EvaluationSuite) -> EvaluationResult:
        effective = candidate or baseline
        response = self.provider.invoke("evaluate", {"documents": {d.relative_path: d.text for d in effective.documents},
            "scenarios": [s.model_dump(mode="json") for s in suite.scenarios]})
        self.last_usage = response.usage
        cases = [EvaluationCaseResult.model_validate(item) for item in cast(list[dict[str, object]], response.data.get("cases", []))]
        return EvaluationResult(engine="semantic-provider", passed=all(c.passed for c in cases), cases=cases,
            raw_summary={"semantic": True, "usage": response.usage.model_dump(mode="json")})


class ProviderPromptSubOptimizer:
    def __init__(self, provider: SemanticProvider) -> None: self.provider, self.last_usage = provider, ProviderUsage(requests=0)
    def optimize(self, prompt: PromptArtifact, evals: EvaluationSuite, budget: SearchConfig) -> PromptOptimizationResult:
        response = self.provider.invoke("optimize_prompt", {"artifact": prompt.model_dump(mode="json"),
            "scenarios": [s.model_dump(mode="json") for s in evals.scenarios], "budget": budget.model_dump(mode="json")})
        self.last_usage = response.usage
        text = str(response.data.get("optimized_text", prompt.text))
        return PromptOptimizationResult(artifact_id=prompt.id, optimized_text=text, changed=text != prompt.text,
            metadata={"provider_usage": response.usage.model_dump(mode="json")})
