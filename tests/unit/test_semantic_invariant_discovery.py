from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.optimizer.invariants import Invariant, InvariantImportance, extract_invariants
from ai_doc.optimizer.semantic import ProviderSemanticInvariantService
from ai_doc.providers.semantic import ProviderUsage, SemanticResponse
from ai_doc.tokens.counter import ApproximateTokenCounter


class DuplicateSemanticDiscoverer:
    def discover(self, snapshot: DocumentationSnapshot) -> list[Invariant]:
        document = snapshot.documents[0]
        return [
            Invariant(
                id="semantic-duplicate",
                source_path=document.relative_path,
                source_section="Rules",
                text="MUST run validation before merge.",
                importance=InvariantImportance.CRITICAL,
                confidence=0.99,
                discovery_source="semantic",
                evidence="MUST run validation before merge.",
                rationale="Validation is a release safety requirement.",
            )
        ]


class DiscoveryProvider:
    def __init__(self, invariants: list[dict[str, object]]) -> None:
        self.invariants = invariants

    def invoke(self, operation: str, _payload: dict[str, object]) -> SemanticResponse:
        assert operation == "discover_invariants"
        return SemanticResponse(
            data={"invariants": self.invariants},
            usage=ProviderUsage(requests=1, input_tokens=10, output_tokens=5),
        )


def _snapshot(tmp_path: Path, text: str) -> DocumentationSnapshot:
    (tmp_path / "AGENTS.md").write_text(f"# Rules\n\n{text}\n", encoding="utf-8")
    return discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())


def _raw_invariant(
    *,
    text: str,
    evidence: str,
    source_path: str = "AGENTS.md",
    rationale: str = "This behavior is required for a safe release.",
) -> dict[str, object]:
    return {
        "id": "semantic-critical",
        "source_path": source_path,
        "source_section": "Rules",
        "text": text,
        "importance": "critical",
        "confidence": 0.99,
        "evidence": evidence,
        "rationale": rationale,
    }


def test_literal_and_semantic_duplicate_become_one_hard_constraint(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "MUST run validation before merge.")
    invariants = extract_invariants(snapshot, DuplicateSemanticDiscoverer())
    assert len(invariants) == 1
    assert invariants[0].discovery_source == "literal"


def test_grounded_implicit_critical_instruction_is_accepted(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "Validate migrations before completion.")
    service = ProviderSemanticInvariantService(
        DiscoveryProvider(
            [
                _raw_invariant(
                    text="Migration changes require validation before completion.",
                    evidence="Validate migrations before completion.",
                )
            ]
        )
    )
    discovered = service.discover(snapshot)
    assert len(discovered) == 1
    assert discovered[0].discovery_source == "semantic"
    assert discovered[0].evidence == "Validate migrations before completion."
    assert discovered[0].rationale


def test_provider_cannot_promote_ordinary_description_without_critical_source_cue(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "The repository contains migration documentation.")
    service = ProviderSemanticInvariantService(
        DiscoveryProvider(
            [
                _raw_invariant(
                    text="Migration documentation MUST be preserved.",
                    evidence="The repository contains migration documentation.",
                )
            ]
        )
    )
    assert service.discover(snapshot) == []


def test_semantic_discovery_rejects_nonexistent_source_path(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "Validate migrations before completion.")
    service = ProviderSemanticInvariantService(
        DiscoveryProvider(
            [
                _raw_invariant(
                    text="Migration changes require validation before completion.",
                    evidence="Validate migrations before completion.",
                    source_path="docs/missing.md",
                )
            ]
        )
    )
    assert service.discover(snapshot) == []


def test_semantic_discovery_rejects_ungrounded_evidence(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "Validate migrations before completion.")
    service = ProviderSemanticInvariantService(
        DiscoveryProvider(
            [
                _raw_invariant(
                    text="Production deploys require two approvals.",
                    evidence="Production deploys require two approvals before release.",
                )
            ]
        )
    )
    assert service.discover(snapshot) == []
