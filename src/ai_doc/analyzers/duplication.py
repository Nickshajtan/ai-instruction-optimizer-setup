from __future__ import annotations

import re
from collections import defaultdict

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.tokens.counter import ApproximateTokenCounter

MIN_DUPLICATE_PARAGRAPH_LENGTH = 60
MIN_DUPLICATE_LIST_ITEM_LENGTH = 20
CODE_PLACEHOLDER = "`code`"
FINOPS_DUPLICATE_PARAGRAPH = "FINOPS_DUPLICATE_PARAGRAPH"
FINOPS_DUPLICATE_LIST_ITEM = "FINOPS_DUPLICATE_LIST_ITEM"


class DuplicationAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        paragraph_locations: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        item_locations: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
        for document in context.snapshot.documents:
            for section in document.sections:
                section_name = section.heading.title if section.heading else None
                for paragraph in _paragraphs(section.text):
                    normalized = _normalize(paragraph)
                    if len(normalized) > MIN_DUPLICATE_PARAGRAPH_LENGTH:
                        paragraph_locations[normalized].append(
                            (document.relative_path, section_name)
                        )
                for item in _list_items(section.text):
                    normalized = _normalize(item)
                    if len(normalized) > MIN_DUPLICATE_LIST_ITEM_LENGTH:
                        item_locations[normalized].append((document.relative_path, section_name))
        for normalized, locations in paragraph_locations.items():
            if len(locations) > 1:
                first_path, first_section = locations[0]
                findings.append(
                    Finding(
                        code=FINOPS_DUPLICATE_PARAGRAPH,
                        category=FindingCategory.FINOPS,
                        severity=FindingSeverity.WARNING,
                        path=first_path,
                        section=first_section,
                        message="Repeated paragraph appears in multiple documentation locations.",
                        evidence={
                            "occurrences": len(locations),
                            "duplicate_tokens": ApproximateTokenCounter().count(normalized),
                        },
                        suggestion="Keep one canonical version and route to it from other locations.",
                    )
                )
        for _normalized, locations in item_locations.items():
            if len(locations) > 1:
                first_path, first_section = locations[0]
                findings.append(
                    Finding(
                        code=FINOPS_DUPLICATE_LIST_ITEM,
                        category=FindingCategory.FINOPS,
                        severity=FindingSeverity.WARNING,
                        path=first_path,
                        section=first_section,
                        message="Duplicated list item increases always-loaded context.",
                        evidence={"occurrences": len(locations)},
                        suggestion="Remove duplicated bullets unless the repetition is intentional for safety.",
                    )
                )
        return findings


def estimate_duplicate_tokens(context: AnalysisContext) -> int:
    seen: dict[str, int] = {}
    duplicates = 0
    counter = ApproximateTokenCounter()
    for document in context.snapshot.documents:
        for paragraph in _paragraphs(document.text):
            normalized = _normalize(paragraph)
            if len(normalized) <= MIN_DUPLICATE_PARAGRAPH_LENGTH:
                continue
            tokens = counter.count(normalized)
            if normalized in seen:
                duplicates += tokens
            else:
                seen[normalized] = tokens
    return duplicates


def _paragraphs(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"\n\s*\n", text)
        if part.strip() and not part.strip().startswith("#")
    ]


def _list_items(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"^\s*[-*]\s+(.+)$", text, flags=re.MULTILINE)
    ]


def _normalize(text: str) -> str:
    text = re.sub(r"`[^`]+`", CODE_PLACEHOLDER, text.lower())
    return re.sub(r"\s+", " ", text).strip()
