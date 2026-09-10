from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from ai_doc.domain.documents import Document, DocumentationSnapshot
from ai_doc.domain.optimization import InvariantDecision


class InvariantImportance(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    NORMAL = "normal"


class InvariantSemanticStatus(StrEnum):
    PRESERVED = "preserved"
    WEAKENED = "weakened"
    REMOVED = "removed"
    UNCERTAIN = "uncertain"


class Invariant(BaseModel):
    id: str
    source_path: str
    source_section: str | None
    text: str
    importance: InvariantImportance
    confidence: float = Field(ge=0, le=1)


class SemanticInvariantVerifier(Protocol):
    def verify(self, invariant: Invariant, candidate: DocumentationSnapshot) -> InvariantSemanticStatus: ...


class SemanticInvariantDiscoverer(Protocol):
    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]: ...


CRITICAL_RE = re.compile(r"\b(MUST|NEVER|REQUIRED|FORBIDDEN)\b", re.IGNORECASE)
IMPORTANT_RE = re.compile(r"\b(SHOULD|IMPORTANT|WARNING)\b", re.IGNORECASE)
MIN_INVARIANT_SENTENCE_LENGTH = 12


def extract_invariants(
    snapshot: DocumentationSnapshot, semantic_discoverer: SemanticInvariantDiscoverer | None = None
) -> list[Invariant]:
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
                    invariants.append(Invariant(id=f"inv-{counter}", source_path=document.relative_path,
                        source_section=section_name, text=sentence.strip(), importance=importance, confidence=confidence))
                    counter += 1
    if semantic_discoverer is not None:
        existing = {_normalize(item.text) for item in invariants}
        for item in semantic_discoverer.discover(snapshot):
            if _normalize(item.text) not in existing:
                invariants.append(item)
                existing.add(_normalize(item.text))
    return invariants


def verify_invariants(invariants: list[Invariant], documents: list[Document]) -> list[str]:
    candidate_text = "\n".join(document.text for document in documents).lower()
    return [item.id for item in invariants if item.importance == InvariantImportance.CRITICAL
            and _normalize(item.text) not in _normalize(candidate_text)]


def verify_invariants_with_evidence(
    invariants: list[Invariant], candidate: DocumentationSnapshot, semantic_verifier: SemanticInvariantVerifier | None,
) -> tuple[list[str], list[InvariantDecision]]:
    literal_missing = set(verify_invariants(invariants, list(candidate.documents)))
    unsafe: list[str] = []
    decisions: list[InvariantDecision] = []
    by_id = {item.id: item for item in invariants}
    for invariant in invariants:
        if invariant.importance != InvariantImportance.CRITICAL:
            continue
        if invariant.id not in literal_missing:
            decisions.append(InvariantDecision(invariant_id=invariant.id, status="preserved", source="literal"))
            continue
        if semantic_verifier is None:
            unsafe.append(invariant.id)
            decisions.append(InvariantDecision(invariant_id=invariant.id, status="removed", source="literal"))
            continue
        status = semantic_verifier.verify(by_id[invariant.id], candidate)
        decisions.append(InvariantDecision(invariant_id=invariant.id, status=status.value, source="semantic"))
        if status != InvariantSemanticStatus.PRESERVED:
            unsafe.append(invariant.id)
    return sorted(unsafe), decisions


def verify_invariants_with_semantics(
    invariants: list[Invariant], candidate: DocumentationSnapshot, semantic_verifier: SemanticInvariantVerifier | None,
) -> list[str]:
    return verify_invariants_with_evidence(invariants, candidate, semantic_verifier)[0]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n(?=\s*(?:[-*]|\d+\.|\w))", text)
    return [part.strip(" -*\t\r\n") for part in parts if len(part.strip()) > MIN_INVARIANT_SENTENCE_LENGTH]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
