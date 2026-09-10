from __future__ import annotations

import re
from decimal import Decimal
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

SEMANTIC_INVARIANT_CONFIDENCE = 0.8
SEMANTIC_CRITICAL_CUE_RE = re.compile(
    r"\b(must|never|required|requires?|cannot|only|before|after|validate|validation|ensure|preserve|"
    r"avoid|prohibit(?:ed)?|forbid(?:den)?|do not|don't)\b",
    re.IGNORECASE,
)


class ProviderSemanticCandidateGenerator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
        strategy: GenerationStrategyName,
        previous_summaries: list[str],
        explored_transformations: list[str],
        feedback: OptimizationFeedback | None,
        memory: SearchMemory,
    ) -> tuple[CandidateProposal, dict[str, str]]:
        response = self.provider.invoke(
            "generate_candidate",
            {
                "strategy": strategy.value,
                "documents": {document.relative_path: document.text for document in snapshot.documents},
                "invariants": [item.model_dump(mode="json") for item in invariants],
                "previous_summaries": previous_summaries,
                "explored_transformations": explored_transformations,
                "feedback": feedback.model_dump(mode="json") if feedback else None,
                "search_memory": memory.model_dump(mode="json"),
            },
        )
        self.last_usage = response.usage
        proposal = CandidateProposal.model_validate(response.data.get("proposal"))
        return proposal, cast(dict[str, str], response.data.get("documents", {}))


class ProviderSemanticInvariantService:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)
        self.usage_history: list[ProviderUsage] = []

    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]:
        documents = {document.relative_path: document.text for document in snapshot.documents}
        response = self.provider.invoke("discover_invariants", {"documents": documents})
        self._record(response.usage)
        result: list[Invariant] = []
        for raw in cast(list[dict[str, object]], response.data.get("invariants", [])):
            item = Invariant.model_validate(raw)
            if self._is_grounded_critical(item, documents):
                result.append(item.model_copy(update={"discovery_source": "semantic"}))
        return result

    def verify(self, invariant: Invariant, candidate: DocumentationSnapshot) -> InvariantSemanticStatus:
        response = self.provider.invoke(
            "verify_invariant",
            {
                "invariant": invariant.model_dump(mode="json"),
                "documents": {document.relative_path: document.text for document in candidate.documents},
                "statuses": [status.value for status in InvariantSemanticStatus],
            },
        )
        self._record(response.usage)
        return InvariantSemanticStatus(str(response.data.get("status", "uncertain")))

    def drain_usage(self) -> ProviderUsage:
        usage = _combine_usage(self.usage_history)
        self.usage_history.clear()
        return usage

    def _record(self, usage: ProviderUsage) -> None:
        self.last_usage = usage
        self.usage_history.append(usage)

    def _is_grounded_critical(self, item: Invariant, documents: dict[str, str]) -> bool:
        if (
            item.importance != InvariantImportance.CRITICAL
            or item.confidence < SEMANTIC_INVARIANT_CONFIDENCE
            or not item.rationale
            or not item.evidence
        ):
            return False
        source = documents.get(item.source_path)
        if source is None:
            return False
        normalized_source = _normalize(source)
        normalized_evidence = _normalize(item.evidence)
        if normalized_evidence not in normalized_source:
            return False
        return bool(SEMANTIC_CRITICAL_CUE_RE.search(f"{item.evidence}\n{item.text}"))


class ProviderSemanticEvaluator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        effective = candidate or baseline
        response = self.provider.invoke(
            "evaluate",
            {
                "documents": {document.relative_path: document.text for document in effective.documents},
                "scenarios": [scenario.model_dump(mode="json") for scenario in suite.scenarios],
            },
        )
        self.last_usage = response.usage
        cases = [
            EvaluationCaseResult.model_validate(item)
            for item in cast(list[dict[str, object]], response.data.get("cases", []))
        ]
        return EvaluationResult(
            engine="semantic-provider",
            passed=all(case.passed for case in cases),
            cases=cases,
            raw_summary={"semantic": True, "usage": response.usage.model_dump(mode="json")},
        )


class ProviderPromptSubOptimizer:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)

    def optimize(
        self,
        prompt: PromptArtifact,
        evals: EvaluationSuite,
        budget: SearchConfig,
    ) -> PromptOptimizationResult:
        response = self.provider.invoke(
            "optimize_prompt",
            {
                "artifact": prompt.model_dump(mode="json"),
                "scenarios": [scenario.model_dump(mode="json") for scenario in evals.scenarios],
                "budget": budget.model_dump(mode="json"),
            },
        )
        self.last_usage = response.usage
        text = str(response.data.get("optimized_text", prompt.text))
        return PromptOptimizationResult(
            artifact_id=prompt.id,
            optimized_text=text,
            changed=text != prompt.text,
            metadata={"provider_usage": response.usage.model_dump(mode="json")},
        )


def _combine_usage(items: list[ProviderUsage]) -> ProviderUsage:
    sources = {item.cost_source for item in items}
    cost_source = "mixed" if len(sources) > 1 else (items[0].cost_source if items else "provider")
    return ProviderUsage(
        requests=sum(item.requests for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        cost_usd=sum((item.cost_usd for item in items), Decimal("0")),
        cost_source=cost_source,
        cache_hits=sum(item.cache_hits for item in items),
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
