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


class EvaluationMode(StrEnum):
    LEXICAL = "lexical"
    MODEL_GRADED = "model_graded"


class BudgetConfig(BaseModel):
    warning_tokens: int | None = None
    error_tokens: int | None = None


class EvaluationBudgetConfig(BaseModel):
    max_requests: int | None = Field(default=None, ge=0)
    max_input_tokens: int | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=0)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)

    def has_limits(self) -> bool:
        return any(
            value is not None
            for value in (
                self.max_requests,
                self.max_input_tokens,
                self.max_output_tokens,
                self.max_cost_usd,
            )
        )


class EvaluationModeConfig(BaseModel):
    engine: EvaluationEngine = EvaluationEngine.PROMPTFOO
    evaluator: str | None = None
    model: str | None = None
    mode: EvaluationMode = EvaluationMode.LEXICAL
    assertion: str | None = None
    budget: EvaluationBudgetConfig = Field(default_factory=EvaluationBudgetConfig)


class LocalMLConfig(BaseModel):
    enabled: bool = False
    semantic_duplication: bool = True
    semantic_contradiction: bool = True
    similarity_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    nli_model: str = "cross-encoder/nli-deberta-v3-small"
    similarity_threshold: float = Field(default=0.90, ge=0, le=1)
    nli_confidence_threshold: float = Field(default=0.90, ge=0, le=1)


class OptimizationConfig(BaseModel):
    engine: EvaluationEngine = EvaluationEngine.DEEPEVAL
    deepeval_model: str | None = None
    pairwise_semantic: bool = False
    gated_pairwise: bool = False
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


class CommandExtensionConfig(BaseModel):
    type: str = "command"
    command: list[str]
    timeout: float = Field(default=120, gt=0)
    env: dict[str, str] = Field(default_factory=dict)


class ComponentSelectionConfig(BaseModel):
    token_counter: str = "approximate"
    recommendation_policy: str = "default"
    provider: str | None = None


class ExtensionRuntimeConfig(BaseModel):
    analyzers: dict[str, CommandExtensionConfig] = Field(default_factory=dict)
    evaluators: dict[str, CommandExtensionConfig] = Field(default_factory=dict)
    token_counters: dict[str, CommandExtensionConfig] = Field(default_factory=dict)
    recommendation_policies: dict[str, CommandExtensionConfig] = Field(default_factory=dict)
    providers: dict[str, CommandExtensionConfig] = Field(default_factory=dict)


class ObservabilityConfig(BaseModel):
    enabled: bool = False
    path: str = ".ai-doc/observations.jsonl"


class AiDocConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    include: list[str] = Field(
        default_factory=lambda: [
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
            ".ai/**/*.md",
            ".codex/**/*.md",
            ".claude/**/*.md",
            ".gemini/**/*.md",
            ".agents/skills/**/SKILL.md",
            ".github/copilot-instructions.md",
            ".github/instructions/**/*.instructions.md",
            ".cursor/rules/**/*.mdc",
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
    local_ml: LocalMLConfig = Field(default_factory=LocalMLConfig)
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
    components: ComponentSelectionConfig = Field(default_factory=ComponentSelectionConfig)
    extension_runtime: ExtensionRuntimeConfig = Field(default_factory=ExtensionRuntimeConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


DEFAULT_CONFIG = AiDocConfig(
    profiles={
        "CLAUDE.md": DocumentProfile.INSTRUCTION,
        "AGENTS.md": DocumentProfile.INSTRUCTION,
        "docs/AGENTS.md": DocumentProfile.INSTRUCTION,
        "docs/CLAUDE.md": DocumentProfile.INSTRUCTION,
        "GEMINI.md": DocumentProfile.INSTRUCTION,
        "docs/GEMINI.md": DocumentProfile.INSTRUCTION,
        ".ai/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".codex/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".claude/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".gemini/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".agents/skills/**/SKILL.md": DocumentProfile.SKILL,
        ".github/copilot-instructions.md": DocumentProfile.INSTRUCTION,
        ".github/instructions/**/*.instructions.md": DocumentProfile.INSTRUCTION,
        ".cursor/rules/**/*.mdc": DocumentProfile.INSTRUCTION,
        "docs/adr/**": DocumentProfile.ADR,
        "docs/**": DocumentProfile.REFERENCE,
    },
    budgets={
        DocumentProfile.INSTRUCTION: BudgetConfig(warning_tokens=3000, error_tokens=6000),
        DocumentProfile.SKILL: BudgetConfig(warning_tokens=3500),
        DocumentProfile.REFERENCE: BudgetConfig(warning_tokens=None),
    },
)
