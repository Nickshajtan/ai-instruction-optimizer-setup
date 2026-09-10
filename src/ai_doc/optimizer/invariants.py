from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from ai_doc.domain.documents import Document, DocumentationSnapshot


class InvariantImportance(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    NORMAL = "normal"


class Invariant(BaseModel):
    id: str
    source_path: str
    source_section: str | None
    text: str
    importance: InvariantImportance
    confidence: float = Field(ge=0, le=1)


CRITICAL_RE = re.compile(r"\b(MUST|NEVER|REQUIRED|FORBIDDEN)\b", re.IGNORECASE)
IMPORTANT_RE = re.compile(r"\b(SHOULD|IMPORTANT|WARNING)\b", re.IGNORECASE)


def extract_invariants(snapshot: DocumentationSnapshot) -> list[Invariant]:
    invariants: list[Invariant] = []
    counter = 1
    for document in snapshot.documents:
        for section in document.sections or ():
            section_name = section.heading.title if section.heading else None
            for sentence in _sentences(section.text):
                importance: InvariantImportance | None = None
                confidence = 0.55
                if CRITICAL_RE.search(sentence):
                    importance = InvariantImportance.CRITICAL
                    confidence = 0.95
                elif IMPORTANT_RE.search(sentence):
                    importance = InvariantImportance.IMPORTANT
                    confidence = 0.8
                if importance:
                    invariants.append(
                        Invariant(
                            id=f"inv-{counter}",
                            source_path=document.relative_path,
                            source_section=section_name,
                            text=sentence.strip(),
                            importance=importance,
                            confidence=confidence,
                        )
                    )
                    counter += 1
    return invariants


def verify_invariants(invariants: list[Invariant], documents: list[Document]) -> list[str]:
    candidate_text = "\n".join(document.text for document in documents).lower()
    missing: list[str] = []
    for invariant in invariants:
        if invariant.importance != InvariantImportance.CRITICAL:
            continue
        normalized = _normalize(invariant.text)
        if normalized not in _normalize(candidate_text):
            missing.append(invariant.id)
    return missing


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n(?=\s*(?:[-*]|\d+\.|\w))", text)
    return [part.strip(" -*\t\r\n") for part in parts if len(part.strip()) > 12]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
