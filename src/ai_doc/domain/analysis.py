from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TextUnitKind(StrEnum):
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    HEADING = "heading"
    CODE_BLOCK = "code_block"


class Modality(StrEnum):
    MUST = "must"
    ALWAYS = "always"
    REQUIRED = "required"
    NEVER = "never"
    FORBIDDEN = "forbidden"


class Polarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class NormalizationPolicy(StrEnum):
    LITERAL_PROPOSITION = "literal_proposition"
    DUPLICATION = "duplication"


@dataclass(frozen=True)
class TextUnit:
    text: str
    normalized_text: str
    kind: TextUnitKind
    path: str
    section: str | None


@dataclass(frozen=True)
class InstructionUnit:
    text: str
    normalized_text: str
    kind: TextUnitKind
    path: str
    section: str | None
    modality: Modality
    polarity: Polarity
    proposition: str
