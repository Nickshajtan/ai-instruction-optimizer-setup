from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.analysis import TextUnitKind
from ai_doc.domain.documents import Document
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.markdown.extraction import extract_text_units
from ai_doc.tokens.counter import ApproximateTokenCounter

MIN_DUPLICATE_PARAGRAPH_LENGTH = 60
MIN_DUPLICATE_LIST_ITEM_LENGTH = 20
HEADING_LESS_DOCUMENT_TOKENS = 100
FINOPS_DUPLICATE_PARAGRAPH = "FINOPS_DUPLICATE_PARAGRAPH"
FINOPS_DUPLICATE_LIST_ITEM = "FINOPS_DUPLICATE_LIST_ITEM"


@dataclass(frozen=True)
class DuplicateLocation:
    path: str
    section: str | None
    structural_headingless: bool


class DuplicationAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        paragraph_locations: dict[str, list[DuplicateLocation]] = defaultdict(list)
        item_locations: dict[str, list[DuplicateLocation]] = defaultdict(list)
        for document in context.snapshot.documents:
            location = DuplicateLocation(
                path=document.relative_path,
                section=None,
                structural_headingless=_substantial_headingless_document(document),
            )
            for unit in extract_text_units(document):
                locations = paragraph_locations if unit.kind == TextUnitKind.PARAGRAPH else item_locations
                minimum = (
                    MIN_DUPLICATE_PARAGRAPH_LENGTH
                    if unit.kind == TextUnitKind.PARAGRAPH
                    else MIN_DUPLICATE_LIST_ITEM_LENGTH
                )
                if unit.kind in {TextUnitKind.PARAGRAPH, TextUnitKind.LIST_ITEM} and len(unit.normalized_text) > minimum:
                    locations[unit.normalized_text].append(
                        DuplicateLocation(
                            path=unit.path,
                            section=unit.section,
                            structural_headingless=location.structural_headingless,
                        )
                    )
        return _duplicate_findings(paragraph_locations, item_locations)


def estimate_duplicate_tokens(context: AnalysisContext) -> int:
    seen: dict[str, int] = {}
    duplicates = 0
    counter = ApproximateTokenCounter()
    for document in context.snapshot.documents:
        for unit in extract_text_units(document):
            if unit.kind != TextUnitKind.PARAGRAPH or len(unit.normalized_text) <= MIN_DUPLICATE_PARAGRAPH_LENGTH:
                continue
            tokens = counter.count(unit.normalized_text)
            if unit.normalized_text in seen:
                duplicates += tokens
            else:
                seen[unit.normalized_text] = tokens
    return duplicates


def _duplicate_findings(
    paragraphs: dict[str, list[DuplicateLocation]],
    items: dict[str, list[DuplicateLocation]],
) -> list[Finding]:
    findings: list[Finding] = []
    for normalized, locations in paragraphs.items():
        if len(locations) > 1:
            first = locations[0]
            findings.append(
                Finding(
                    code=FINOPS_DUPLICATE_PARAGRAPH,
                    category=FindingCategory.FINOPS,
                    severity=FindingSeverity.WARNING,
                    path=first.path,
                    section=first.section,
                    message="Repeated paragraph appears in multiple documentation locations.",
                    evidence={
                        "occurrences": len(locations),
                        "duplicate_tokens": ApproximateTokenCounter().count(normalized),
                    },
                    suggestion="Keep one canonical version and route to it from other locations.",
                )
            )
    for locations in items.values():
        if len(locations) > 1:
            unique_locations = list(dict.fromkeys(locations))
            if _is_local_unnamed_scope_duplicate(unique_locations):
                continue
            first = unique_locations[0]
            findings.append(
                Finding(
                    code=FINOPS_DUPLICATE_LIST_ITEM,
                    category=FindingCategory.FINOPS,
                    severity=FindingSeverity.WARNING,
                    path=first.path,
                    section=first.section,
                    message="Duplicated list item increases always-loaded context.",
                    evidence={
                        "occurrences": len(locations),
                        "duplicate_scopes": len(unique_locations),
                    },
                    suggestion="Remove duplicated bullets unless the repetition is intentional for safety.",
                )
            )
    return findings


def _is_local_unnamed_scope_duplicate(locations: list[DuplicateLocation]) -> bool:
    return len(locations) == 1 and locations[0].section is None and locations[0].structural_headingless


def _substantial_headingless_document(document: Document) -> bool:
    return document.token_count >= HEADING_LESS_DOCUMENT_TOKENS and not document.headings
