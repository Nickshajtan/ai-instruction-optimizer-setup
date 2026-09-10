from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.optimizer.invariants import Invariant, InvariantImportance, extract_invariants
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


def test_literal_and_semantic_duplicate_become_one_hard_constraint(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\nMUST run validation before merge.\n",
        encoding="utf-8",
    )
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(snapshot, DuplicateSemanticDiscoverer())
    assert len(invariants) == 1
    assert invariants[0].discovery_source == "literal"
