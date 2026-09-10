from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.optimization import OptimizationFeedback, SearchMemory
from ai_doc.domain.proposals import CandidateProposal, OperationType, ProposalOperation, RiskLevel
from ai_doc.optimizer.invariants import Invariant, InvariantImportance

EXAMPLES_MIN_TOKENS = 350
EXTRACTED_DOCS_DIR = "docs/ai-doc-extracted"
EXAMPLE_HEADING_KEYWORD = "example"
STRENGTHEN_FEEDBACK_KEYWORD = "strengthen"
INSTRUCTION_PROFILES = {DocumentProfile.INSTRUCTION, DocumentProfile.SKILL}
LOW_RISK: RiskLevel = "low"
MEDIUM_RISK: RiskLevel = "medium"
OBJECTIVE_CLARITY = "clarity"
OBJECTIVE_CONTEXT_COST = "context_cost"
OBJECTIVE_RELIABILITY = "reliability"


class GenerationStrategyName(StrEnum):
    CONSERVATIVE = "conservative"
    CLARITY = "clarity"
    FINOPS = "finops"
    BALANCED = "balanced"


class CandidateGenerationStrategy(Protocol):
    name: GenerationStrategyName

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        ...


def _operation(
    operation_type: OperationType,
    reason: str,
    expected_clarity_effect: str,
    expected_finops_effect: str,
    risk: RiskLevel,
    target: str | None = None,
    sources: list[str] | None = None,
    objective: list[str] | None = None,
    trigger: str | None = None,
) -> ProposalOperation:
    return ProposalOperation(
        type=operation_type,
        target=target,
        sources=sources or [],
        reason=reason,
        expected_clarity_effect=expected_clarity_effect,
        expected_finops_effect=expected_finops_effect,
        risk=risk,
        objective=objective or [],
        trigger=trigger,
    )


class ConservativeCandidateGenerator:
    name = GenerationStrategyName.CONSERVATIVE

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        invariant_texts = {
            invariant.text.strip()
            for invariant in invariants
            if invariant.importance == InvariantImportance.CRITICAL
        }
        operations: list[ProposalOperation] = []
        rendered: dict[str, str] = {}
        extracted: dict[str, str] = {}
        for document in snapshot.documents:
            text = document.text
            text, deduped = _deduplicate_lines(text, invariant_texts)
            if deduped:
                operations.append(
                    _operation(
                        operation_type="deduplicate",
                        target=document.relative_path,
                        reason="Repeated bullets or paragraphs were found in the same document.",
                        expected_clarity_effect="Reduces repeated instructions while retaining the first occurrence.",
                        expected_finops_effect="Lowers repeated always-loaded tokens.",
                        risk=LOW_RISK,
                    )
                )
            if document.profile == DocumentProfile.INSTRUCTION:
                text, new_files, new_ops = _extract_large_examples(document, text)
                extracted.update(new_files)
                operations.extend(new_ops)
            rendered[document.relative_path] = text
        rendered.update(extracted)
        if not operations:
            operations.append(
                _operation(
                    operation_type="retain",
                    reason="No low-risk deterministic optimization was found.",
                    expected_clarity_effect="Preserves current structure.",
                    expected_finops_effect="No material token change.",
                    risk=LOW_RISK,
                )
            )
        return CandidateProposal(operations=operations), rendered


class ClarityCandidateGenerator:
    name = GenerationStrategyName.CLARITY

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        del invariants
        rendered = {document.relative_path: document.text for document in snapshot.documents}
        return _clarity_from_rendered(snapshot, rendered)


class FinOpsCandidateGenerator:
    name = GenerationStrategyName.FINOPS

    def __init__(self, conservative: CandidateGenerationStrategy | None = None) -> None:
        self.conservative = conservative or ConservativeCandidateGenerator()

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        proposal, rendered = self.conservative.generate(snapshot, invariants)
        operations = list(proposal.operations)
        for document in snapshot.documents:
            if document.profile != DocumentProfile.INSTRUCTION:
                continue
            text = rendered[document.relative_path]
            compressed = re.sub(r"\n{3,}", "\n\n", text)
            compressed = re.sub(r"(?im)^Example [A-Z]: ", "- ", compressed)
            if compressed != text:
                rendered[document.relative_path] = compressed
                operations.append(
                    _operation(
                        operation_type="compress",
                        target=document.relative_path,
                        reason="Instruction file still contains verbose example prose.",
                        expected_clarity_effect="Keeps examples scannable as bullets.",
                        expected_finops_effect="Reduces always-loaded wording.",
                        risk=MEDIUM_RISK,
                        objective=[OBJECTIVE_CONTEXT_COST],
                    )
                )
        return CandidateProposal(operations=operations), rendered


class BalancedCandidateGenerator:
    name = GenerationStrategyName.BALANCED

    def __init__(
        self,
        conservative: CandidateGenerationStrategy | None = None,
    ) -> None:
        self.conservative = conservative or ConservativeCandidateGenerator()

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        proposal, rendered = self.conservative.generate(snapshot, invariants)
        clarity_proposal, clarity_rendered = _clarity_from_rendered(snapshot, rendered)
        return (
            CandidateProposal(operations=[*proposal.operations, *clarity_proposal.operations]),
            clarity_rendered,
        )


class FeedbackRepairCandidateGenerator:
    name = GenerationStrategyName.BALANCED

    def generate_from_feedback(
        self,
        snapshot: DocumentationSnapshot,
        feedback: OptimizationFeedback,
    ) -> tuple[CandidateProposal, dict[str, str]]:
        rendered = {document.relative_path: document.text for document in snapshot.documents}
        operations: list[ProposalOperation] = []
        directions = " ".join(feedback.suggested_mutation_directions).lower()
        for document in snapshot.documents:
            if document.profile != DocumentProfile.INSTRUCTION or STRENGTHEN_FEEDBACK_KEYWORD not in directions:
                continue
            text = rendered[document.relative_path]
            updated = re.sub(
                r"When detailed ([^.]+) are needed, read",
                r"When changing, debugging, or validating \1, MUST read",
                text,
                flags=re.IGNORECASE,
            )
            if updated != text:
                rendered[document.relative_path] = updated
                operations.append(
                    _operation(
                        operation_type="strengthen_router",
                        target=document.relative_path,
                        reason="Parent feedback indicated the extracted reference router was too weak.",
                        expected_clarity_effect="Makes the trigger explicit without restoring the full section.",
                        expected_finops_effect="Preserves extraction savings with a short stronger router.",
                        risk=LOW_RISK,
                        objective=[OBJECTIVE_RELIABILITY, OBJECTIVE_CLARITY],
                    )
                )
        if not operations:
            operations.append(
                _operation(
                    operation_type="retain",
                    reason=f"Feedback for {feedback.candidate_id} did not identify a deterministic mutation.",
                    expected_clarity_effect="Preserves parent behavior.",
                    expected_finops_effect="No additional savings.",
                    risk=LOW_RISK,
                )
            )
        return CandidateProposal(operations=operations), rendered


class StrategyCandidateGenerator:
    def __init__(
        self,
        strategies: dict[GenerationStrategyName, CandidateGenerationStrategy] | None = None,
        fallback: CandidateGenerationStrategy | None = None,
        feedback_strategy: FeedbackRepairCandidateGenerator | None = None,
    ) -> None:
        conservative = ConservativeCandidateGenerator()
        self.strategies = strategies or {
            GenerationStrategyName.CONSERVATIVE: conservative,
            GenerationStrategyName.CLARITY: ClarityCandidateGenerator(),
            GenerationStrategyName.FINOPS: FinOpsCandidateGenerator(conservative),
            GenerationStrategyName.BALANCED: BalancedCandidateGenerator(conservative),
        }
        self.fallback = fallback or conservative
        self.feedback_strategy = feedback_strategy or FeedbackRepairCandidateGenerator()

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
        strategy: str | GenerationStrategyName,
        previous_summaries: list[str] | None = None,
        explored_transformations: list[str] | None = None,
        feedback: OptimizationFeedback | None = None,
        memory: SearchMemory | None = None,
    ) -> tuple[CandidateProposal, dict[str, str]]:
        del previous_summaries, explored_transformations, memory
        if feedback:
            return self.feedback_strategy.generate_from_feedback(snapshot, feedback)
        strategy_name = _strategy_name(strategy)
        selected = self.strategies.get(strategy_name, self.fallback)
        return selected.generate(snapshot, invariants)


def _strategy_name(strategy: str | GenerationStrategyName) -> GenerationStrategyName:
    if isinstance(strategy, GenerationStrategyName):
        return strategy
    try:
        return GenerationStrategyName(strategy)
    except ValueError:
        return GenerationStrategyName.CONSERVATIVE


def _clarity_from_rendered(
    snapshot: DocumentationSnapshot,
    rendered: dict[str, str],
) -> tuple[CandidateProposal, dict[str, str]]:
    operations: list[ProposalOperation] = []
    for document in snapshot.documents:
        if document.profile not in INSTRUCTION_PROFILES:
            continue
        text = rendered[document.relative_path]
        updated = re.sub(
            r"\bUse best practices\b",
            "Follow the concrete validation, testing, and routing rules documented here",
            text,
            flags=re.IGNORECASE,
        )
        updated = re.sub(r"\bshould\b", "SHOULD", updated)
        updated = re.sub(r"\bmust\b", "MUST", updated)
        updated = re.sub(r"\bmay\b", "MAY", updated)
        if updated != text:
            rendered[document.relative_path] = updated
            operations.append(
                _operation(
                    operation_type="rewrite",
                    target=document.relative_path,
                    reason="Ambiguous or inconsistent instruction wording was detected.",
                    expected_clarity_effect="Makes rules more explicit and terminology more consistent.",
                    expected_finops_effect="May slightly change tokens depending on wording.",
                    risk=LOW_RISK,
                    objective=[OBJECTIVE_CLARITY],
                )
            )
    if not operations:
        operations.append(
            _operation(
                operation_type="retain",
                reason="No deterministic clarity rewrite was available.",
                expected_clarity_effect="Preserves existing clarity.",
                expected_finops_effect="No context change.",
                risk=LOW_RISK,
            )
        )
    return CandidateProposal(operations=operations), rendered


def _deduplicate_lines(text: str, invariant_texts: set[str]) -> tuple[str, bool]:
    seen: set[str] = set()
    changed = False
    output: list[str] = []
    for line in text.splitlines():
        normalized = re.sub(r"\s+", " ", line.strip().lower())
        is_candidate = line.lstrip().startswith(("-", "*")) and len(normalized) > 20
        if is_candidate and normalized in seen and line.strip(" -*") not in invariant_texts:
            changed = True
            continue
        if is_candidate:
            seen.add(normalized)
        output.append(line)
    return "\n".join(output) + ("\n" if text.endswith("\n") else ""), changed


def _extract_large_examples(
    document: Document,
    text: str,
) -> tuple[str, dict[str, str], list[ProposalOperation]]:
    lines = text.splitlines()
    new_files: dict[str, str] = {}
    operations: list[ProposalOperation] = []
    for section in document.sections:
        if (
            not section.heading
            or EXAMPLE_HEADING_KEYWORD not in section.heading.title.lower()
            or section.token_count < EXAMPLES_MIN_TOKENS
        ):
            continue
        start = section.start_line - 1
        end = section.end_line
        slug = re.sub(r"[^a-z0-9]+", "-", section.heading.title.lower()).strip("-") or "examples"
        target = f"{EXTRACTED_DOCS_DIR}/{Path(document.relative_path).stem}-{slug}.md"
        extracted = "\n".join(lines[start:end]).rstrip() + "\n"
        new_files[target] = extracted
        heading_prefix = "#" * section.heading.level
        replacement = [
            f"{heading_prefix} {section.heading.title}",
            "",
            f"When detailed examples are needed, read [{section.heading.title}]({target}).",
        ]
        lines[start:end] = replacement
        operations.extend(
            [
                _operation(
                    operation_type="extract",
                    sources=[f"{document.relative_path}#{section.heading.title}"],
                    target=target,
                    reason="Large examples are low-frequency detail for an instruction profile.",
                    expected_clarity_effect="Keeps the instruction file focused while preserving examples.",
                    expected_finops_effect="Moves verbose material out of always-loaded context.",
                    risk=MEDIUM_RISK,
                ),
                _operation(
                    operation_type="add_router",
                    target=document.relative_path,
                    trigger=f"When detailed {section.heading.title.lower()} are needed",
                    reason="Extracted material needs a discoverable route.",
                    expected_clarity_effect="Makes on-demand reference discovery explicit.",
                    expected_finops_effect="Keeps only a short router in always-loaded context.",
                    risk=LOW_RISK,
                ),
            ]
        )
        break
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), new_files, operations
