from __future__ import annotations

from collections import Counter

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity

LARGE_FILE_TOKENS = 8000
LARGE_SECTION_TOKENS = 1800
MAX_HEADING_LEVEL_JUMP = 1
ROOT_INSTRUCTION_FILES = {"AGENTS.md", "CLAUDE.md"}
AI_DOC_PROFILES = {DocumentProfile.INSTRUCTION, DocumentProfile.SKILL}

STRUCTURE_LARGE_FILE = "STRUCTURE_LARGE_FILE"
STRUCTURE_LARGE_SECTION = "STRUCTURE_LARGE_SECTION"
STRUCTURE_HEADING_JUMP = "STRUCTURE_HEADING_JUMP"
STRUCTURE_DUPLICATE_SECTION = "STRUCTURE_DUPLICATE_SECTION"
STRUCTURE_BROKEN_LOCAL_LINK = "STRUCTURE_BROKEN_LOCAL_LINK"
STRUCTURE_ORPHANED_AI_DOC = "STRUCTURE_ORPHANED_AI_DOC"


class StructureAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            if document.token_count > LARGE_FILE_TOKENS:
                findings.append(
                    Finding(
                        code=STRUCTURE_LARGE_FILE,
                        category=FindingCategory.STRUCTURE,
                        severity=FindingSeverity.WARNING,
                        path=document.relative_path,
                        message="Markdown file is large enough to be difficult to scan.",
                        evidence={"tokens": document.token_count},
                        suggestion="Split low-frequency reference material into focused files.",
                    )
                )
            for section in document.sections:
                if section.token_count > LARGE_SECTION_TOKENS and document.profile != DocumentProfile.ADR:
                    findings.append(
                        Finding(
                            code=STRUCTURE_LARGE_SECTION,
                            category=FindingCategory.STRUCTURE,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            section=section.heading.title if section.heading else None,
                            message="Section is large and may need clearer subdivision.",
                            evidence={"tokens": section.token_count},
                            suggestion="Break the section into named subsections or move examples to reference docs.",
                        )
                    )
            levels = [heading.level for heading in document.headings]
            for previous, current in zip(levels, levels[1:], strict=False):
                if current - previous > MAX_HEADING_LEVEL_JUMP:
                    findings.append(
                        Finding(
                            code=STRUCTURE_HEADING_JUMP,
                            category=FindingCategory.STRUCTURE,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            message="Heading hierarchy jumps by more than one level.",
                            evidence={"from": previous, "to": current},
                            suggestion="Use sequential heading levels for predictable navigation.",
                        )
                    )
            titles = Counter(heading.title.lower() for heading in document.headings)
            for title, count in titles.items():
                if count > 1:
                    findings.append(
                        Finding(
                            code=STRUCTURE_DUPLICATE_SECTION,
                            category=FindingCategory.STRUCTURE,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            section=title,
                            message="Duplicate heading names make routing ambiguous.",
                            evidence={"count": count},
                            suggestion="Rename or merge duplicate sections.",
                        )
                    )
            for link in document.links:
                if link.is_local_markdown and link.exists is False:
                    findings.append(
                        Finding(
                            code=STRUCTURE_BROKEN_LOCAL_LINK,
                            category=FindingCategory.STRUCTURE,
                            severity=FindingSeverity.ERROR,
                            path=document.relative_path,
                            message="Local Markdown link does not resolve.",
                            evidence={"target": link.target, "line": link.line},
                            suggestion="Update the link target or add the referenced file.",
                        )
                    )
            if (
                document.profile in AI_DOC_PROFILES
                and not context.graph.incoming(document)
                and document.relative_path not in ROOT_INSTRUCTION_FILES
            ):
                findings.append(
                    Finding(
                        code=STRUCTURE_ORPHANED_AI_DOC,
                        category=FindingCategory.STRUCTURE,
                        severity=FindingSeverity.INFO,
                        path=document.relative_path,
                        message="Configured AI documentation has no incoming local Markdown links.",
                        evidence={},
                        suggestion="Add a router from an always-loaded instruction file when this doc is on-demand.",
                    )
                )
        return findings
