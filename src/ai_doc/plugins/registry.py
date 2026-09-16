from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from ai_doc.analyzers.base import Analyzer
from ai_doc.domain.evaluations import Evaluator
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.providers.semantic import SemanticProvider
from ai_doc.tokens.counter import TokenCounter


class AnalyzerRegistrationValidator:
    def validate(self, analyzer: object) -> Analyzer:
        analyze = getattr(analyzer, "analyze", None)
        if not callable(analyze):
            raise TypeError("Analyzer registration must provide an object with analyze(context).")
        return cast(Analyzer, analyzer)


class EvaluatorRegistrationValidator:
    def validate(self, evaluator: object) -> Evaluator:
        evaluate = getattr(evaluator, "evaluate", None)
        if not callable(evaluate):
            raise TypeError("Evaluator registration must provide an object with evaluate(baseline, candidate, suite).")
        return cast(Evaluator, evaluator)


class TokenCounterRegistrationValidator:
    def validate(self, token_counter: object) -> TokenCounter:
        count = getattr(token_counter, "count", None)
        if not callable(count):
            raise TypeError("Token counter registration must provide an object with count(text, model=None).")
        return cast(TokenCounter, token_counter)


class RecommendationPolicyRegistrationValidator:
    def validate(self, policy: object) -> RecommendationPolicy:
        choose = getattr(policy, "choose", None)
        if not callable(choose):
            raise TypeError("Recommendation policy registration must provide an object with choose(baseline, frontier).")
        return cast(RecommendationPolicy, policy)


class ProviderRegistrationValidator:
    def validate(self, provider: object) -> SemanticProvider:
        invoke = getattr(provider, "invoke", None)
        if not callable(invoke):
            raise TypeError("Provider registration must provide an object with invoke(operation, payload).")
        return cast(SemanticProvider, provider)


T = TypeVar("T")


@dataclass(frozen=True)
class RegistryEntry[T]:
    name: str
    component: T


class NamedComponentRegistry[T]:
    def __init__(self, kind: str, validator: Callable[[object], T]) -> None:
        self.kind = kind
        self._validator = validator
        self._items: dict[str, T] = {}

    def add(self, name: str, component: object) -> None:
        if not name:
            raise ValueError(f"{self.kind} registration name must not be empty.")
        if name in self._items:
            raise ValueError(f"Duplicate {self.kind} registration: {name}")
        self._items[name] = self._validator(component)

    def resolve(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._items)) or "<none>"
            raise KeyError(f"Unknown {self.kind} registration {name!r}. Available: {available}") from exc

    def entries(self) -> tuple[RegistryEntry[T], ...]:
        return tuple(RegistryEntry(name, self._items[name]) for name in sorted(self._items))


class ExtensionRegistry:
    def __init__(
        self,
        validator: AnalyzerRegistrationValidator | None = None,
        evaluator_validator: EvaluatorRegistrationValidator | None = None,
        token_counter_validator: TokenCounterRegistrationValidator | None = None,
        recommendation_policy_validator: RecommendationPolicyRegistrationValidator | None = None,
        provider_validator: ProviderRegistrationValidator | None = None,
    ) -> None:
        self._validator = validator or AnalyzerRegistrationValidator()
        self._analyzers: list[Analyzer] = []
        self._evaluators = NamedComponentRegistry(
            "evaluator",
            (evaluator_validator or EvaluatorRegistrationValidator()).validate,
        )
        self._token_counters = NamedComponentRegistry(
            "token counter",
            (token_counter_validator or TokenCounterRegistrationValidator()).validate,
        )
        self._recommendation_policies = NamedComponentRegistry(
            "recommendation policy",
            (recommendation_policy_validator or RecommendationPolicyRegistrationValidator()).validate,
        )
        self._providers: NamedComponentRegistry[SemanticProvider] = NamedComponentRegistry(
            "provider",
            (provider_validator or ProviderRegistrationValidator()).validate,
        )

    @property
    def analyzers(self) -> tuple[Analyzer, ...]:
        return tuple(self._analyzers)

    @property
    def evaluators(self) -> tuple[RegistryEntry[Evaluator], ...]:
        return self._evaluators.entries()

    @property
    def token_counters(self) -> tuple[RegistryEntry[TokenCounter], ...]:
        return self._token_counters.entries()

    @property
    def recommendation_policies(self) -> tuple[RegistryEntry[RecommendationPolicy], ...]:
        return self._recommendation_policies.entries()

    @property
    def providers(self) -> tuple[RegistryEntry[SemanticProvider], ...]:
        return self._providers.entries()

    def add_analyzer(self, analyzer: object) -> None:
        self._analyzers.append(self._validator.validate(analyzer))

    def add_evaluator(self, name: str, evaluator: object) -> None:
        self._evaluators.add(name, evaluator)

    def resolve_evaluator(self, name: str) -> Evaluator:
        return self._evaluators.resolve(name)

    def add_token_counter(self, name: str, token_counter: object) -> None:
        self._token_counters.add(name, token_counter)

    def resolve_token_counter(self, name: str) -> TokenCounter:
        return self._token_counters.resolve(name)

    def add_recommendation_policy(self, name: str, policy: object) -> None:
        self._recommendation_policies.add(name, policy)

    def resolve_recommendation_policy(self, name: str) -> RecommendationPolicy:
        return self._recommendation_policies.resolve(name)

    def add_provider(self, name: str, provider: object) -> None:
        self._providers.add(name, provider)

    def resolve_provider(self, name: str) -> SemanticProvider:
        return self._providers.resolve(name)
