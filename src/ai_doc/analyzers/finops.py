from __future__ import annotations

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.domain.scores import ContextCost

ALWAYS_LOADED = {DocumentProfile.INSTRUCTION}
LOADING_MODE_ALWAYS = "always"
APPROXIMATE_COUNTER_LABEL = "approximate"
ALWAYS_LOADED_LARGE_TOKENS = 3000
LARGE_EXAMPLE_MIN_TOKENS = 350
LARGE_EXAMPLE_DOCUMENT_RATIO = 0.25
LARGE_CODE_INSTRUCTION_TOKENS = 250
EXAMPLE_SECTION_KEYWORD = "example"
FENCED_CODE_MARKER = "```"

FINOPS_BUDGET_ERROR = "FINOPS_BUDGET_ERROR"
FINOPS_BUDGET_WARNING = "FINOPS_BUDGET_WARNING"
FINOPS_ALWAYS_LOADED_LARGE = "FINOPS_ALWAYS_LOADED_LARGE"
FINOPS_LARGE_EXAMPLES_SECTION = "FINOPS_LARGE_EXAMPLES_SECTION"
FINOPS_LARGE_CODE_IN_INSTRUCTION = "FINOPS_LARGE_CODE_IN_INSTRUCTION"


class FinOpsAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            budget = context.config.budgets.get(document.profile)
            if budget:
                if budget.error_tokens is not None and document.token_count > budget.error_tokens:
                    severity: FindingSeverity | None = FindingSeverity.ERROR
                    code = FINOPS_BUDGET_ERROR
                elif (
                    budget.warning_tokens is not None
                    and document.token_count > budget.warning_tokens
                ):
                    severity = FindingSeverity.WARNING
                    code = FINOPS_BUDGET_WARNING
                else:
                    severity = None
                    code = ""
                if severity:
                    findings.append(
                        Finding(
                            code=code,
                            category=FindingCategory.FINOPS,
                            severity=severity,
                            path=document.relative_path,
                            message="Document exceeds configured token budget.",
                            evidence={
                                "tokens": document.token_count,
                                "warning_tokens": budget.warning_tokens,
                                "error_tokens": budget.error_tokens,
                                "counter": APPROXIMATE_COUNTER_LABEL,
                            },
                            suggestion=(
                                "Move low-frequency detail to on-demand references or deduplicate "
                                "repeated content."
                            ),
                        )
                    )
            if document.profile in ALWAYS_LOADED and document.token_count > ALWAYS_LOADED_LARGE_TOKENS:
                findings.append(
                    Finding(
                        code=FINOPS_ALWAYS_LOADED_LARGE,
                        category=FindingCategory.FINOPS,
                        severity=FindingSeverity.WARNING,
                        path=document.relative_path,
                        message="Always-loaded instruction document is large.",
                        evidence={"tokens": document.token_count},
                        suggestion="Keep critical rules here and route detailed reference material elsewhere.",
                    )
                )
            for section in document.sections:
                title = (section.heading.title if section.heading else "").lower()
                if EXAMPLE_SECTION_KEYWORD in title and section.token_count > max(
                    LARGE_EXAMPLE_MIN_TOKENS,
                    int(document.token_count * LARGE_EXAMPLE_DOCUMENT_RATIO),
                ):
                    findings.append(
                        Finding(
                            code=FINOPS_LARGE_EXAMPLES_SECTION,
                            category=FindingCategory.FINOPS,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            section=section.heading.title if section.heading else None,
                            message="Examples section consumes a disproportionate share of the document.",
                            evidence={
                                "section_tokens": section.token_count,
                                "document_tokens": document.token_count,
                            },
                            suggestion=(
                                "Extract lengthy examples to an on-demand reference and link to it "
                                "from a short router."
                            ),
                        )
                    )
                if (
                    document.profile == DocumentProfile.INSTRUCTION
                    and FENCED_CODE_MARKER in section.text
                    and section.token_count > LARGE_CODE_INSTRUCTION_TOKENS
                ):
                    findings.append(
                        Finding(
                            code=FINOPS_LARGE_CODE_IN_INSTRUCTION,
                            category=FindingCategory.FINOPS,
                            severity=FindingSeverity.WARNING,
                            path=document.relative_path,
                            section=section.heading.title if section.heading else None,
                            message="Instruction profile contains large fenced-code content.",
                            evidence={"section_tokens": section.token_count},
                            suggestion="Move long code examples to reference documentation.",
                        )
                    )
        return findings


def calculate_context_cost(context: AnalysisContext, duplicate_tokens: int) -> ContextCost:
    raw = context.snapshot.total_tokens
    always = sum(
        document.token_count
        for document in context.snapshot.documents
        if document.profile in ALWAYS_LOADED
        or context.config.loading.get(document.relative_path, None)
        and context.config.loading[document.relative_path].mode == LOADING_MODE_ALWAYS
    )
    referenced = raw - always
    expected: float | None = None
    probabilities = [
        config.probability
        for config in context.config.loading.values()
        if config.probability is not None
    ]
    if probabilities:
        by_path = context.snapshot.by_relative_path()
        expected = 0.0
        for path, document in by_path.items():
            loading = context.config.loading.get(path)
            if loading and loading.probability is not None:
                expected += document.token_count * loading.probability
    return ContextCost(
        raw_tokens=raw,
        always_loaded_tokens=always,
        referenced_tokens=referenced,
        duplicate_tokens=duplicate_tokens,
        estimated_context_tokens=expected,
    )
