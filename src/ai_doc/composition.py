from __future__ import annotations

import os
from decimal import Decimal

from ai_doc.config.models import AiDocConfig
from ai_doc.domain.evaluations import Evaluator
from ai_doc.evaluators.deepeval import DeepEvalEvaluator
from ai_doc.evaluators.promptfoo import PromptfooEvaluator
from ai_doc.extensions.process import (
    ProcessAnalyzer,
    ProcessEvaluator,
    ProcessRecommendationPolicy,
    ProcessSemanticProvider,
    ProcessTokenCounter,
    ProcessTransport,
)
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.providers.semantic import (
    SEMANTIC_COMMAND_ENV,
    BudgetedSemanticProvider,
    CommandSemanticProvider,
    SemanticProvider,
)
from ai_doc.tokens.counter import ApproximateTokenCounter, TokenCounter

BUILTIN_TOKEN_COUNTER_APPROXIMATE = "approximate"
BUILTIN_EVALUATOR_PROMPTFOO = "promptfoo"
BUILTIN_EVALUATOR_DEEPEVAL = "deepeval"
BUILTIN_RECOMMENDATION_DEFAULT = "default"
BUILTIN_PROVIDER_SEMANTIC_COMMAND = "semantic-command"


def register_configured_extensions(config: AiDocConfig, registry: ExtensionRegistry) -> ExtensionRegistry:
    _register_builtins(registry)
    for name, analyzer in config.extension_runtime.analyzers.items():
        registry.add_analyzer(
            ProcessAnalyzer(_transport(name, "analyzer", analyzer.type, analyzer.command, analyzer.timeout))
        )
    for name, evaluator in config.extension_runtime.evaluators.items():
        registry.add_evaluator(
            name,
            ProcessEvaluator(
                _transport(name, "evaluator", evaluator.type, evaluator.command, evaluator.timeout),
                engine=name,
            ),
        )
    for name, counter in config.extension_runtime.token_counters.items():
        registry.add_token_counter(
            name,
            ProcessTokenCounter(
                _transport(name, "token counter", counter.type, counter.command, counter.timeout),
                label=name,
            ),
        )
    for name, policy in config.extension_runtime.recommendation_policies.items():
        registry.add_recommendation_policy(
            name,
            ProcessRecommendationPolicy(
                _transport(name, "recommendation policy", policy.type, policy.command, policy.timeout)
            ),
        )
    for name, provider in config.extension_runtime.providers.items():
        registry.add_provider(
            name,
            ProcessSemanticProvider(_transport(name, "provider", provider.type, provider.command, provider.timeout)),
        )
    return registry


def resolve_configured_evaluator(
    config: AiDocConfig,
    registry: ExtensionRegistry,
    mode: str,
) -> Evaluator | None:
    selected = config.evaluation.get(mode)
    if selected is None or selected.evaluator is None:
        return None
    return registry.resolve_evaluator(selected.evaluator)


def resolve_token_counter(config: AiDocConfig, registry: ExtensionRegistry | None = None) -> TokenCounter:
    if registry is None:
        registry = register_configured_extensions(config, ExtensionRegistry())
    return registry.resolve_token_counter(config.components.token_counter)


def resolve_recommendation_policy(
    config: AiDocConfig,
    registry: ExtensionRegistry | None,
    default_policy: RecommendationPolicy,
) -> RecommendationPolicy:
    selected = config.components.recommendation_policy
    if selected == BUILTIN_RECOMMENDATION_DEFAULT:
        return default_policy
    if registry is None:
        registry = register_configured_extensions(config, ExtensionRegistry())
    return registry.resolve_recommendation_policy(selected)


def resolve_semantic_provider(
    config: AiDocConfig,
    registry: ExtensionRegistry,
    *,
    max_requests: int,
    max_input_tokens: int | None = None,
    max_output_tokens: int | None = None,
    max_cost_usd: Decimal | None = None,
) -> SemanticProvider | None:
    selected = config.components.provider
    if selected is None:
        selected = BUILTIN_PROVIDER_SEMANTIC_COMMAND if os.getenv(SEMANTIC_COMMAND_ENV) else None
    if selected is None:
        return None
    provider = registry.resolve_provider(selected)
    return BudgetedSemanticProvider(
        provider,
        max_requests,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        max_cost_usd=max_cost_usd,
    )


def _register_builtins(registry: ExtensionRegistry) -> None:
    registry.add_token_counter(BUILTIN_TOKEN_COUNTER_APPROXIMATE, ApproximateTokenCounter())
    registry.add_evaluator(BUILTIN_EVALUATOR_PROMPTFOO, PromptfooEvaluator())
    registry.add_evaluator(BUILTIN_EVALUATOR_DEEPEVAL, DeepEvalEvaluator())
    registry.add_recommendation_policy(BUILTIN_RECOMMENDATION_DEFAULT, RecommendationPolicy())
    if os.getenv(SEMANTIC_COMMAND_ENV):
        registry.add_provider(BUILTIN_PROVIDER_SEMANTIC_COMMAND, CommandSemanticProvider())


def _transport(name: str, capability: str, extension_type: str, command: list[str], timeout: float) -> ProcessTransport:
    if extension_type != "command":
        raise ValueError(f"Unsupported {capability} extension type for {name!r}: {extension_type!r}")
    return ProcessTransport(command, timeout=timeout)
