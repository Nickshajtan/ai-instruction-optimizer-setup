from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class NLIRelation(StrEnum):
    CONTRADICTION = "contradiction"
    ENTAILMENT = "entailment"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class NLIResult:
    relation: NLIRelation
    confidence: float


class SemanticSimilarityEngine(Protocol):
    def similarity(self, left: str, right: str) -> float: ...


class NLIEngine(Protocol):
    def classify(self, premise: str, hypothesis: str) -> NLIResult: ...
