from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_doc.config.search import (
    GepaConfig,
    OptimizeMode,
    ParetoConfig,
    PopulationConfig,
    RecommendationConfig,
    SearchConfig,
)
from ai_doc.domain.documents import DocumentProfile


class EvaluationEngine(StrEnum):
    PROMPTFOO = "promptfoo"
    DEEPEVAL = "deepeval"


class BudgetConfig(BaseModel):
    warning_tokens: int | None = None
    error_tokens: int | None = None


class EvaluationModeConfig(BaseModel):
    engine: EvaluationEngine = EvaluationEngine.PROMPTFOO


class OptimizationConfig(BaseModel):
    engine: EvaluationEngine = EvaluationEngine.DEEPEVAL
    strategy: OptimizeMode = OptimizeMode.BALANCED
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    gepa: GepaConfig = Field(default_factory=GepaConfig)
    pareto: ParetoConfig = Field(default_factory=ParetoConfig)
    recommendation: RecommendationConfig = Field(default_factory=RecommendationConfig)
    exploration_rate: float = Field(default=0.25, ge=0, le=1)
    restart_after_stagnation: bool = False
    concurrency: int = Field(default=3, ge=1)


class PricingConfig(BaseModel):
    input_per_million: Decimal = Decimal("0")
    output_per_million: Decimal = Decimal("0")


class LoadingConfig(BaseModel):
    mode: str = "on_demand"
    probability: float | None = Field(default=None, ge=0, le=1)


class ExtensionConfig(BaseModel):
    path: str


class AiDocConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    include: list[str] = Field(
        default_factory=lambda: [
            "AGENTS.md",
            "CLAUDE.md",
            ".ai/**/*.md",
            ".codex/**/*.md",
            ".claude/**/*.md",
            "docs/**/*.md",
        ]
    )
    exclude: list[str] = Field(
        default_factory=lambda: [
            "node_modules/**",
            "vendor/**",
            "build/**",
            "dist/**",
            ".ai-doc-output/**",
            ".tools/ai-doc/**",
        ]
    )
    profiles: dict[str, DocumentProfile] = Field(default_factory=dict)
    budgets: dict[DocumentProfile, BudgetConfig] = Field(default_factory=dict)
    evaluation: dict[str, EvaluationModeConfig] = Field(
        default_factory=lambda: {
            "fast": EvaluationModeConfig(),
            "deep": EvaluationModeConfig(),
        }
    )
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    pricing: dict[str, PricingConfig] = Field(default_factory=dict)
    loading: dict[str, LoadingConfig] = Field(default_factory=dict)
    extensions: list[ExtensionConfig] = Field(default_factory=list)


DEFAULT_CONFIG = AiDocConfig(
    profiles={
        "CLAUDE.md": DocumentProfile.INSTRUCTION,
        "AGENTS.md": DocumentProfile.INSTRUCTION,
        "docs/AGENTS.md": DocumentProfile.INSTRUCTION,
        "docs/CLAUDE.md": DocumentProfile.INSTRUCTION,
        ".ai/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".codex/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".claude/skills/**/SKILL.md": DocumentProfile.SKILL,
        "docs/adr/**": DocumentProfile.ADR,
        "docs/**": DocumentProfile.REFERENCE,
    },
    budgets={
        DocumentProfile.INSTRUCTION: BudgetConfig(warning_tokens=3000, error_tokens=6000),
        DocumentProfile.SKILL: BudgetConfig(warning_tokens=3500),
        DocumentProfile.REFERENCE: BudgetConfig(warning_tokens=None),
    },
)
