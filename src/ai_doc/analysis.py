from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ai_doc.domain.documents import Document


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
    SHOULD = "should"
    MAY = "may"
    IMPERATIVE = "imperative"


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


class InstructionExtractor(Protocol):
    def extract(self, document: Document) -> list[InstructionUnit]: ...


_INLINE_MARKUP_RE = re.compile(r"[`*_]")
_WHITESPACE_RE = re.compile(r"\s+")
_CODE_RE = re.compile(r"`[^`]+`")
_NORMATIVE_RE = re.compile(
    r"^\s*(?P<modal>must\s+not|never|forbidden\s+to|must|always|required\s+to)\s+(?P<body>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def normalize_text(text: str, policy: NormalizationPolicy) -> str:
    lowered = text.lower()
    if policy == NormalizationPolicy.DUPLICATION:
        return _WHITESPACE_RE.sub(" ", _CODE_RE.sub("`code`", lowered)).strip()
    cleaned = _INLINE_MARKUP_RE.sub("", lowered)
    return _WHITESPACE_RE.sub(" ", cleaned).strip(" .!?")


def classify_literal_instruction(unit: TextUnit, text: str | None = None) -> InstructionUnit | None:
    evidence = (text if text is not None else unit.text).strip()
    match = _NORMATIVE_RE.match(evidence)
    if match is None:
        return None
    modal = match.group("modal").lower()
    modality, polarity = _modality_and_polarity(modal)
    proposition = normalize_text(match.group("body"), NormalizationPolicy.LITERAL_PROPOSITION)
    if len(proposition) < 3:
        return None
    return InstructionUnit(
        text=evidence,
        normalized_text=normalize_text(evidence, NormalizationPolicy.LITERAL_PROPOSITION),
        kind=unit.kind,
        path=unit.path,
        section=unit.section,
        modality=modality,
        polarity=polarity,
        proposition=proposition,
    )


class DeterministicInstructionExtractor:
    """Extract conservative literal normative instructions from parsed text units."""

    def extract(self, document: Document) -> list[InstructionUnit]:
        instructions: list[InstructionUnit] = []
        for unit in document.text_units:
            if unit.kind not in {TextUnitKind.PARAGRAPH, TextUnitKind.LIST_ITEM}:
                continue
            for sentence in _sentence_candidates(unit.text):
                instruction = classify_literal_instruction(unit, sentence)
                if instruction is not None:
                    instructions.append(instruction)
        return instructions


def _sentence_candidates(text: str) -> list[str]:
    """Split an already parsed prose unit without treating Markdown as plain text."""
    candidates: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char not in ".!?" or index + 1 >= len(text) or not text[index + 1].isspace():
            continue
        candidate = text[start : index + 1].strip()
        if candidate:
            candidates.append(candidate)
        start = index + 1
    tail = text[start:].strip()
    if tail:
        candidates.append(tail)
    return candidates


def _modality_and_polarity(modal: str) -> tuple[Modality, Polarity]:
    if modal == "must not":
        return Modality.MUST, Polarity.NEGATIVE
    if modal == "never":
        return Modality.NEVER, Polarity.NEGATIVE
    if modal == "forbidden to":
        return Modality.FORBIDDEN, Polarity.NEGATIVE
    if modal == "must":
        return Modality.MUST, Polarity.POSITIVE
    if modal == "always":
        return Modality.ALWAYS, Polarity.POSITIVE
    return Modality.REQUIRED, Polarity.POSITIVE
