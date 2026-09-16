from __future__ import annotations

import re
from typing import Protocol

from markdown_it import MarkdownIt
from markdown_it.token import Token

from ai_doc.domain.analysis import (
    InstructionUnit,
    Modality,
    NormalizationPolicy,
    Polarity,
    TextUnit,
    TextUnitKind,
)
from ai_doc.domain.documents import Document

_WHITESPACE_RE = re.compile(r"\s+")
_INLINE_MARKUP_RE = re.compile(r"[`*_]")
_CODE_RE = re.compile(r"`[^`]+`")
_NORMATIVE_RE = re.compile(
    r"^\s*(?P<modal>must\s+not|never|forbidden\s+to|must|always|required\s+to)\s+(?P<body>.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def normalize_text(text: str, policy: NormalizationPolicy) -> str:
    lowered = text.lower()
    if policy == NormalizationPolicy.DUPLICATION:
        return _WHITESPACE_RE.sub(" ", _CODE_RE.sub("`code`", lowered)).strip()
    return _WHITESPACE_RE.sub(" ", _INLINE_MARKUP_RE.sub("", lowered)).strip(" .!?")


def extract_text_units(document: Document) -> list[TextUnit]:
    """Extract Markdown blocks from the AST; regex is deliberately not used for structure."""
    tokens = MarkdownIt("commonmark").parse(document.text)
    units: list[TextUnit] = []
    list_depth = 0
    for index, token in enumerate(tokens):
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            list_depth += 1
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            list_depth -= 1
        elif token.type == "heading_open":
            inline = _next_inline(tokens, index)
            if inline is not None:
                units.append(_unit(document, inline, TextUnitKind.HEADING))
        elif token.type == "paragraph_open":
            inline = _next_inline(tokens, index)
            if inline is not None:
                kind = TextUnitKind.LIST_ITEM if list_depth else TextUnitKind.PARAGRAPH
                units.append(_unit(document, inline, kind))
        elif token.type in {"fence", "code_block"}:
            units.append(_unit(document, token, TextUnitKind.CODE_BLOCK))
    return units


class InstructionExtractor(Protocol):
    def extract(self, document: Document) -> list[InstructionUnit]: ...


class DeterministicInstructionExtractor:
    def extract(self, document: Document) -> list[InstructionUnit]:
        instructions: list[InstructionUnit] = []
        for unit in extract_text_units(document):
            if unit.kind not in {TextUnitKind.PARAGRAPH, TextUnitKind.LIST_ITEM}:
                continue
            for candidate in _sentence_candidates(unit.text):
                instruction = classify_literal_instruction(unit, candidate)
                if instruction is not None:
                    instructions.append(instruction)
        return instructions


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


def _unit(document: Document, token: Token, kind: TextUnitKind) -> TextUnit:
    text = token.content.strip()
    section = _section_for_line(document, token.map[0] + 1 if token.map else 1)
    return TextUnit(
        text=text,
        normalized_text=normalize_text(text, NormalizationPolicy.DUPLICATION),
        kind=kind,
        path=document.relative_path,
        section=section,
    )


def _next_inline(tokens: list[Token], index: int) -> Token | None:
    candidate = tokens[index + 1] if index + 1 < len(tokens) else None
    return candidate if candidate is not None and candidate.type == "inline" else None


def _section_for_line(document: Document, line: int) -> str | None:
    for section in document.sections:
        if section.start_line <= line <= section.end_line:
            return section.heading.title if section.heading else None
    return None


def _sentence_candidates(text: str) -> list[str]:
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
