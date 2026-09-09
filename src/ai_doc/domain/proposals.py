from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

OperationType = Literal[
    "rewrite",
    "deduplicate",
    "reorder",
    "extract",
    "inline",
    "add_router",
    "strengthen_router",
    "compress",
    "restore",
    "merge",
    "split",
    "retain",
]
RiskLevel = Literal["low", "medium", "high"]


class ProposalOperation(BaseModel):
    type: OperationType
    target: str | None = None
    sources: list[str] = Field(default_factory=list)
    reason: str
    expected_clarity_effect: str
    expected_finops_effect: str
    risk: RiskLevel
    objective: list[str] = Field(default_factory=list)
    trigger: str | None = None


class CandidateProposal(BaseModel):
    operations: list[ProposalOperation]
