from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class OptimizeMode(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    SEARCH = "search"


class PopulationConfig(BaseModel):
    initial_candidates: int = Field(default=4, ge=1)


class SearchConfig(BaseModel):
    generations: int = Field(default=1, ge=1)
    initial_candidates: int = Field(default=4, ge=1)
    children_per_generation: int = Field(default=3, ge=0)
    max_candidates: int = Field(default=4, ge=1)
    max_llm_requests: int = Field(default=100, ge=0)
    max_input_tokens: int | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: Decimal | None = Decimal("5.00")
    patience: int = Field(default=2, ge=0)


class ParetoConfig(BaseModel):
    tolerances: dict[str, float] = Field(
        default_factory=lambda: {
            "reliability": 0.01,
            "clarity": 0.01,
            "always_loaded_tokens": 100.0,
            "expected_context_tokens": 100.0,
            "critical_invariant_recall": 0.0,
        }
    )
    require_parent_improvement: bool = False


class GepaConfig(BaseModel):
    enabled: bool = False
    iterations: int = Field(default=5, ge=1)
    pareto_size: int = Field(default=3, ge=1)
    minibatch_size: int = Field(default=8, ge=1)
    patience: int = Field(default=3, ge=0)
    random_seed: int | None = 42
    reflection_model: str | None = None
    mutation_model: str | None = None


class RecommendationConfig(BaseModel):
    minimum_reliability_delta: float = -0.01
    minimum_clarity_delta: float = -0.02


class RuntimeSearchConfig(BaseModel):
    mode: OptimizeMode = OptimizeMode.BALANCED
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    pareto: ParetoConfig = Field(default_factory=ParetoConfig)
    gepa: GepaConfig = Field(default_factory=GepaConfig)
    recommendation: RecommendationConfig = Field(default_factory=RecommendationConfig)
    exploration_rate: float = Field(default=0.25, ge=0, le=1)
    restart_after_stagnation: bool = False
    concurrency: int = Field(default=3, ge=1)
    seed: int | None = None
