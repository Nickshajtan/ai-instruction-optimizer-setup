from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FindingCategory(StrEnum):
    CLARITY = "clarity"
    FINOPS = "finops"
    STRUCTURE = "structure"
    RISK = "risk"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Finding(BaseModel):
    code: str = Field(min_length=1)
    category: FindingCategory
    severity: FindingSeverity
    path: str
    section: str | None = None
    message: str
    evidence: dict[str, object] = Field(default_factory=dict)
    suggestion: str | None = None


def severity_rank(severity: FindingSeverity) -> int:
    return {
        FindingSeverity.INFO: 0,
        FindingSeverity.WARNING: 1,
        FindingSeverity.ERROR: 2,
    }[severity]
