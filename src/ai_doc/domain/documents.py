from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class DocumentProfile(StrEnum):
    INSTRUCTION = "instruction"
    SKILL = "skill"
    REFERENCE = "reference"
    ADR = "adr"
    GENERIC = "generic"


class Heading(BaseModel):
    level: int
    title: str
    line: int
    slug: str


class Section(BaseModel):
    heading: Heading | None
    text: str
    token_count: int
    start_line: int
    end_line: int


class DocumentLink(BaseModel):
    label: str
    target: str
    line: int
    resolved_path: str | None = None
    anchor: str | None = None
    is_local_markdown: bool = False
    exists: bool | None = None


class Document(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    relative_path: str
    profile: DocumentProfile
    text: str
    token_count: int
    headings: tuple[Heading, ...] = ()
    sections: tuple[Section, ...] = ()
    links: tuple[DocumentLink, ...] = ()


class DocumentationSnapshot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path
    documents: tuple[Document, ...]

    @property
    def total_tokens(self) -> int:
        return sum(document.token_count for document in self.documents)

    def by_relative_path(self) -> dict[str, Document]:
        return {document.relative_path: document for document in self.documents}
