from __future__ import annotations

import re
from decimal import Decimal
from typing import cast

from ai_doc.config.search import SearchConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import (
    EvaluationCaseResult,
    EvaluationResult,
    EvaluationSuite,
    PairwiseDimension,
    PairwiseDimensionResult,
    PairwiseOutcome,
    PairwiseSemanticResult,
)
from ai_doc.domain.optimization import OptimizationFeedback, SearchMemory
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.generator import GenerationStrategyName
from ai_doc.optimizer.invariants import Invariant, InvariantImportance, InvariantSemanticStatus
from ai_doc.optimizer.prompt_suboptimizer import PromptArtifact, PromptOptimizationResult
from ai_doc.providers.semantic import ProviderUsage, SemanticBudgetExceeded, SemanticProvider

SEMANTIC_INVARIANT_CONFIDENCE = 0.8
SEMANTIC_CRITICAL_CUE_RE = re.compile(
    r"\b(must|never|required|requires?|cannot|validate|validation|ensure|preserve|"
    r"avoid|prohibit(?:ed)?|forbid(?:den)?|do not|don't)\b",
    re.IGNORECASE,
)
PAIRWISE_ENGINE = "semantic-provider-pairwise"
PAIRWISE_DIMENSIONS: tuple[PairwiseDimension, ...] = tuple(PairwiseDimension)


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
        self.budget_exhausted = False

    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]:
        documents = {document.relative_path: document.text for document in snapshot.documents}
        try:
            response = self.provider.invoke("discover_invariants", {"documents": documents})
        except SemanticBudgetExceeded:
            self.budget_exhausted = True
            return []
        self._record(response.usage)
        result: list[Invariant] = []
        for raw in cast(list[dict[str, object]], response.data.get("invariants", [])):
            item = Invariant.model_validate(raw)
            if self._is_grounded_critical(item, documents):
                result.append(item.model_copy(update={"discovery_source": "semantic"}))
        return result

    def verify(self, invariant: Invariant, candidate: DocumentationSnapshot) -> InvariantSemanticStatus:
        try:
            response = self.provider.invoke(
                "verify_invariant",
                {
                    "invariant": invariant.model_dump(mode="json"),
                    "documents": {document.relative_path: document.text for document in candidate.documents},
                    "statuses": [status.value for status in InvariantSemanticStatus],
                },
            )
        except SemanticBudgetExceeded:
            self.budget_exhausted = True
            return InvariantSemanticStatus.UNCERTAIN
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
        # Criticality must be grounded in repository-owned evidence. Provider-authored
        # summary text or confidence cannot manufacture a hard constraint by itself.
        return bool(SEMANTIC_CRITICAL_CUE_RE.search(item.evidence))


class ProviderSemanticEvaluator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)
        self.usage_history: list[ProviderUsage] = []
        self.budget_exhausted = False

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        effective = candidate or baseline
        try:
            response = self.provider.invoke(
                "evaluate",
                {
                    "documents": {document.relative_path: document.text for document in effective.documents},
                    "scenarios": [scenario.model_dump(mode="json") for scenario in suite.scenarios],
                },
            )
        except SemanticBudgetExceeded:
            self.budget_exhausted = True
            self.last_usage = ProviderUsage(requests=0)
            cases = [
                EvaluationCaseResult(
                    id=scenario.id,
                    passed=False,
                    score=None,
                    message="semantic provider budget exhausted before evaluation",
                )
                for scenario in suite.scenarios
            ]
            return EvaluationResult(
                engine="semantic-provider",
                passed=False,
                cases=cases,
                raw_summary={"semantic": True, "budget_exhausted": True},
            )
        self.last_usage = response.usage
        self.usage_history.append(response.usage)
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

    def drain_usage(self) -> ProviderUsage:
        usage = _combine_usage(self.usage_history)
        self.usage_history.clear()
        return usage


class ProviderPairwiseSemanticEvaluator:
    def __init__(self, provider: SemanticProvider) -> None:
        self.provider = provider
        self.last_usage = ProviderUsage(requests=0)
        self.usage_history: list[ProviderUsage] = []
        self.budget_exhausted = False

    def compare_pairwise(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot,
        suite: EvaluationSuite,
    ) -> PairwiseSemanticResult:
        try:
            response = self.provider.invoke(
                "compare_pairwise",
                {
                    "baseline_documents": {document.relative_path: document.text for document in baseline.documents},
                    "candidate_documents": {document.relative_path: document.text for document in candidate.documents},
                    "scenarios": [scenario.model_dump(mode="json") for scenario in suite.scenarios],
                    "dimensions": [dimension.value for dimension in PAIRWISE_DIMENSIONS],
                    "outcomes": [outcome.value for outcome in PairwiseOutcome],
                    "rubric": _pairwise_rubric(),
                },
            )
        except SemanticBudgetExceeded:
            self.budget_exhausted = True
            return uncertain_pairwise_result(
                PAIRWISE_ENGINE, "semantic provider budget exhausted before pairwise comparison"
            )
        self._record(response.usage)
        return normalize_pairwise_response(
            response.data,
            engine=PAIRWISE_ENGINE,
            unavailable_reason="semantic provider returned no pairwise evidence",
        )

    def drain_usage(self) -> ProviderUsage:
        usage = _combine_usage(self.usage_history)
        self.usage_history.clear()
        return usage

    def _record(self, usage: ProviderUsage) -> None:
        self.last_usage = usage
        self.usage_history.append(usage)


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


def normalize_pairwise_response(
    data: dict[str, object],
    *,
    engine: str,
    unavailable_reason: str | None = None,
) -> PairwiseSemanticResult:
    raw_dimensions = data.get("dimensions", [])
    by_dimension: dict[PairwiseDimension, PairwiseDimensionResult] = {}
    if isinstance(raw_dimensions, list):
        for raw in raw_dimensions:
            if not isinstance(raw, dict):
                continue
            dimension = _dimension(raw.get("dimension"))
            by_dimension[dimension] = PairwiseDimensionResult(
                dimension=dimension,
                outcome=_outcome(raw.get("outcome")),
                evidence=_evidence(raw.get("evidence") or raw.get("reason")),
            )
    dimensions = [
        by_dimension.get(
            dimension,
            PairwiseDimensionResult(
                dimension=dimension,
                outcome=PairwiseOutcome.UNCERTAIN,
                evidence="No evidence supplied for this dimension.",
            ),
        )
        for dimension in PAIRWISE_DIMENSIONS
    ]
    overall = _outcome(data.get("overall") or data.get("winner") or data.get("outcome"))
    reason: str | None
    if overall == PairwiseOutcome.UNCERTAIN and unavailable_reason:
        reason = str(data.get("reason") or unavailable_reason)
    else:
        reason = str(data.get("reason")) if data.get("reason") is not None else None
    return PairwiseSemanticResult(
        engine=engine,
        overall=overall,
        dimensions=dimensions,
        reason=reason,
        raw_summary={key: value for key, value in data.items() if key not in {"dimensions"}},
    )


def uncertain_pairwise_result(engine: str, reason: str) -> PairwiseSemanticResult:
    return PairwiseSemanticResult(
        engine=engine,
        overall=PairwiseOutcome.UNCERTAIN,
        dimensions=[
            PairwiseDimensionResult(
                dimension=dimension,
                outcome=PairwiseOutcome.UNCERTAIN,
                evidence=reason,
            )
            for dimension in PAIRWISE_DIMENSIONS
        ],
        reason=reason,
        raw_summary={"semantic": True, "uncertain": True},
    )


def _pairwise_rubric() -> dict[str, str]:
    return {
        "claim_boundary": "Predict instruction-following quality only; do not claim empirical target-agent success.",
        "clarity": "Which version is easier for an agent to understand accurately?",
        "ambiguity": "Which version leaves fewer plausible but unintended interpretations?",
        "scope_precision": "Which version defines applicability and boundaries more precisely?",
        "instruction_hierarchy": "Which version preserves priority between rules, defaults, and exceptions better?",
        "actionability": "Which version makes the expected action more directly executable?",
        "semantic_requirement_preservation": (
            "Which version better preserves the baseline's required and forbidden behavior?"
        ),
        "conflicting_interpretation_risk": "Which version is less likely to support conflicting interpretations?",
    }


def _dimension(value: object) -> PairwiseDimension:
    try:
        return PairwiseDimension(str(value))
    except ValueError:
        return PairwiseDimension.CLARITY


def _outcome(value: object) -> PairwiseOutcome:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "candidate_wins": PairwiseOutcome.CANDIDATE,
        "candidate_better": PairwiseOutcome.CANDIDATE,
        "candidate": PairwiseOutcome.CANDIDATE,
        "baseline_wins": PairwiseOutcome.BASELINE,
        "baseline_better": PairwiseOutcome.BASELINE,
        "baseline": PairwiseOutcome.BASELINE,
        "tie": PairwiseOutcome.EQUIVALENT,
        "equal": PairwiseOutcome.EQUIVALENT,
        "equivalent": PairwiseOutcome.EQUIVALENT,
        "unclear": PairwiseOutcome.UNCERTAIN,
        "unknown": PairwiseOutcome.UNCERTAIN,
        "uncertain": PairwiseOutcome.UNCERTAIN,
    }
    return aliases.get(normalized, PairwiseOutcome.UNCERTAIN)


def _evidence(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "No concise evidence supplied."


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
