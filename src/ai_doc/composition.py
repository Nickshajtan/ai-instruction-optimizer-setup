from __future__ import annotations

from ai_doc.config.models import AiDocConfig
from ai_doc.domain.evaluations import Evaluator
from ai_doc.extensions.process import ProcessEvaluator
from ai_doc.plugins.registry import ExtensionRegistry


def register_configured_extensions(config: AiDocConfig, registry: ExtensionRegistry) -> ExtensionRegistry:
    for name, evaluator in config.extension_runtime.evaluators.items():
        if evaluator.type != "command":
            raise ValueError(f"Unsupported evaluator extension type for {name!r}: {evaluator.type!r}")
        registry.add_evaluator(
            name,
            ProcessEvaluator(evaluator.command, timeout=evaluator.timeout, engine=name),
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
