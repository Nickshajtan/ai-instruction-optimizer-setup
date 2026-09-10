from __future__ import annotations

import re

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity

VAGUE_RE = re.compile(
    r"\b(follow|use)\s+best\s+practices\b|\bappropriate validation\b", re.IGNORECASE
)
ACTION_RE = re.compile(
    r"\b(must|never|should|use|run|write|read|check|verify|avoid|prefer|do not)\b", re.IGNORECASE
)
UPPERCASE_MODAL_RE = re.compile(r"\bMUST\b|\bSHOULD\b|\bMAY\b")
LOWERCASE_MODAL_RE = re.compile(r"\b(?:must|should|may)\b")

INSTRUCTION_PROFILES = {DocumentProfile.INSTRUCTION, DocumentProfile.SKILL}
LIST_OR_HEADING_PREFIXES = ("#", "-", "*", "```")
LONG_PROSE_LINES = 12
LONG_PROSE_TOKENS = 500
ACTIONABLE_SECTION_TOKENS = 40
AMBIGUOUS_LINK_LABELS = {"here", "this", "link", "docs", "more"}
VAGUE_PATTERN_LABEL = "best practices / appropriate validation"

CLARITY_INCONSISTENT_MODAL_VOCABULARY = "CLARITY_INCONSISTENT_MODAL_VOCABULARY"
CLARITY_AMBIGUOUS_RULE = "CLARITY_AMBIGUOUS_RULE"
CLARITY_EXCESSIVE_NESTED_PROSE = "CLARITY_EXCESSIVE_NESTED_PROSE"
CLARITY_NO_ACTIONABLE_CONTENT = "CLARITY_NO_ACTIONABLE_CONTENT"
ROUTING_AMBIGUOUS_LINK_LABEL = "ROUTING_AMBIGUOUS_LINK_LABEL"


class ClarityAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            uppercase_modal_count = len(UPPERCASE_MODAL_RE.findall(document.text))
            lower_modal_count = len(LOWERCASE_MODAL_RE.findall(document.text))
            if uppercase_modal_count and lower_modal_count:
                findings.append(
                    Finding(
                        code=CLARITY_INCONSISTENT_MODAL_VOCABULARY,
                        category=FindingCategory.CLARITY,
                        severity=FindingSeverity.WARNING,
                        path=document.relative_path,
                        message="Instruction language mixes RFC-style uppercase modals with lowercase usage.",
                        evidence={
                            "uppercase": uppercase_modal_count,
                            "lowercase": lower_modal_count,
                        },
                        suggestion="Use MUST/SHOULD/MAY consistently when the terms are normative.",
                    )
                )
            for section in document.sections:
                section_name = section.heading.title if section.heading else None
                if VAGUE_RE.search(section.text):
                    findings.append(
                        Finding(
                            code=CLARITY_AMBIGUOUS_RULE,
                            category=FindingCategory.CLARITY,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            section=section_name,
                            message="Rule uses vague wording without a local definition.",
                            evidence={"pattern": VAGUE_PATTERN_LABEL},
                            suggestion="Name the concrete rule, command, or routing target.",
                        )
                    )
                if document.profile in INSTRUCTION_PROFILES:
                    prose_lines = [
                        line
                        for line in section.text.splitlines()
                        if line.strip() and not line.lstrip().startswith(LIST_OR_HEADING_PREFIXES)
                    ]
                    if len(prose_lines) > LONG_PROSE_LINES and section.token_count > LONG_PROSE_TOKENS:
                        findings.append(
                            Finding(
                                code=CLARITY_EXCESSIVE_NESTED_PROSE,
                                category=FindingCategory.CLARITY,
                                severity=FindingSeverity.WARNING,
                                path=document.relative_path,
                                section=section_name,
                                message="Instruction section contains a long prose block.",
                                evidence={"lines": len(prose_lines), "tokens": section.token_count},
                                suggestion=(
                                    "Convert operational rules to bullets and move background context "
                                    "to reference docs."
                                ),
                            )
                        )
                    body = "\n".join(section.text.splitlines()[1:])
                    if (
                        section.heading
                        and section.token_count > ACTIONABLE_SECTION_TOKENS
                        and not ACTION_RE.search(body)
                    ):
                        findings.append(
                            Finding(
                                code=CLARITY_NO_ACTIONABLE_CONTENT,
                                category=FindingCategory.CLARITY,
                                severity=FindingSeverity.WARNING,
                                path=document.relative_path,
                                section=section_name,
                                message="Instruction section has no clear action-oriented content.",
                                evidence={},
                                suggestion=(
                                    "Add explicit action rules or reclassify this material as "
                                    "reference content."
                                ),
                            )
                        )
                for link in document.links:
                    if link.is_local_markdown and link.label.lower() in AMBIGUOUS_LINK_LABELS:
                        findings.append(
                            Finding(
                                code=ROUTING_AMBIGUOUS_LINK_LABEL,
                                category=FindingCategory.CLARITY,
                                severity=FindingSeverity.WARNING,
                                path=document.relative_path,
                                message="Local documentation link has an ambiguous label.",
                                evidence={"label": link.label, "target": link.target},
                                suggestion="Use a label that states the trigger or destination purpose.",
                            )
                        )
        return findings
