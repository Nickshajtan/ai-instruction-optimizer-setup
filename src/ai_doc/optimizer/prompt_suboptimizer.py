from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field

from ai_doc.config.search import GepaConfig, SearchConfig
from ai_doc.domain.evaluations import EvaluationSuite

DEFAULT_REFLECTION_MODEL = "gpt-4o-mini"
DEFAULT_MUTATION_MODEL = "gpt-4o"
DEEPEVAL_PACKAGE = "deepeval"
DEEPEVAL_UNAVAILABLE_MESSAGE = "DeepEval GEPA is unavailable. Install ai-doc[deepeval]."
PROMPT_ROLE = "instruction-fragment"
METADATA_SEED_KEY = "seed"
METADATA_GEPA_KEY = "gepa"
METADATA_DEEPEVAL_VERSION_KEY = "deepeval_version"


class PromptArtifact(BaseModel):
    id: str
    text: str
    role: str = PROMPT_ROLE


class PromptOptimizationResult(BaseModel):
    artifact_id: str
    optimized_text: str
    changed: bool
    metadata: dict[str, object] = Field(default_factory=dict)


class PromptSubOptimizer(Protocol):
    def optimize(
        self,
        prompt: PromptArtifact,
        evals: EvaluationSuite,
        budget: SearchConfig,
    ) -> PromptOptimizationResult:
        ...


@dataclass(frozen=True)
class DeepEvalGEPASymbols:
    golden: Callable[..., Any]
    answer_relevancy_metric: Callable[..., Any]
    prompt_optimizer: Callable[..., Any]
    gepa: Callable[..., Any]
    prompt: Callable[..., Any]


class DeepEvalGEPAPromptOptimizer:
    def __init__(self, config: GepaConfig) -> None:
        self.config = config

    def optimize(
        self,
        prompt: PromptArtifact,
        evals: EvaluationSuite,
        budget: SearchConfig,
    ) -> PromptOptimizationResult:
        symbols = _load_deepeval_gepa_symbols()

        def model_callback(de_prompt: Any, golden: Any) -> str:
            return str(de_prompt.interpolate(input=golden.input))

        algorithm = symbols.gepa(
            iterations=min(self.config.iterations, budget.max_llm_requests or self.config.iterations),
            pareto_size=self.config.pareto_size,
            minibatch_size=self.config.minibatch_size,
            patience=self.config.patience,
            random_seed=self.config.random_seed,
            reflection_model=self.config.reflection_model or DEFAULT_REFLECTION_MODEL,
            mutation_model=self.config.mutation_model or DEFAULT_MUTATION_MODEL,
        )
        optimizer = symbols.prompt_optimizer(
            algorithm=algorithm,
            model_callback=model_callback,
            metrics=[symbols.answer_relevancy_metric()],
        )
        goldens = [
            symbols.golden(input=scenario.task, expected_output="\n".join(scenario.expected_required))
            for scenario in evals.scenarios
        ]
        if not goldens:
            return PromptOptimizationResult(
                artifact_id=prompt.id,
                optimized_text=prompt.text,
                changed=False,
                metadata=self._metadata(),
            )
        optimized = optimizer.optimize(prompt=symbols.prompt(text_template=prompt.text), goldens=goldens)
        optimized_text = getattr(optimized, "text_template", prompt.text)
        return PromptOptimizationResult(
            artifact_id=prompt.id,
            optimized_text=optimized_text,
            changed=optimized_text != prompt.text,
            metadata=self._metadata(),
        )

    def _metadata(self) -> dict[str, object]:
        try:
            version = importlib.metadata.version(DEEPEVAL_PACKAGE)
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
        return {
            METADATA_SEED_KEY: self.config.random_seed,
            METADATA_GEPA_KEY: self.config.model_dump(),
            METADATA_DEEPEVAL_VERSION_KEY: version,
        }


def _load_deepeval_gepa_symbols() -> DeepEvalGEPASymbols:
    try:
        dataset = import_module("deepeval.dataset")
        metrics = import_module("deepeval.metrics")
        optimizer = import_module("deepeval.optimizer")
        algorithms = import_module("deepeval.optimizer.algorithms")
        prompt = import_module("deepeval.prompt")
    except ImportError as exc:
        raise RuntimeError(DEEPEVAL_UNAVAILABLE_MESSAGE) from exc
    dataset_api = cast(Any, dataset)
    metrics_api = cast(Any, metrics)
    optimizer_api = cast(Any, optimizer)
    algorithms_api = cast(Any, algorithms)
    prompt_api = cast(Any, prompt)
    return DeepEvalGEPASymbols(
        golden=cast(Callable[..., Any], dataset_api.Golden),
        answer_relevancy_metric=cast(Callable[..., Any], metrics_api.AnswerRelevancyMetric),
        prompt_optimizer=cast(Callable[..., Any], optimizer_api.PromptOptimizer),
        gepa=cast(Callable[..., Any], algorithms_api.GEPA),
        prompt=cast(Callable[..., Any], prompt_api.Prompt),
    )
