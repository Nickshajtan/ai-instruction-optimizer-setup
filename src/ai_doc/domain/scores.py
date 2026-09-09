from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class ContextCost(BaseModel):
    raw_tokens: int
    always_loaded_tokens: int
    referenced_tokens: int
    duplicate_tokens: int
    estimated_context_tokens: float | None = None
    estimated_cost: Decimal | None = None


class ScoreSet(BaseModel):
    clarity_errors: int
    clarity_warnings: int
    finops_warnings: int
    structure_errors: int
    total_tokens: int
    always_loaded_tokens: int
    duplicate_tokens: int
