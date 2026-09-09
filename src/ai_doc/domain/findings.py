from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FindingCategory = Literal["clarity", "finops", "structure", "risk"]
FindingSeverity = Literal["info", "warning", "error"]


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
    return {"info": 0, "warning": 1, "error": 2}[severity]
