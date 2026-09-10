from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
from ai_doc.optimizer.generator import (
    ConservativeCandidateGenerator,
    GenerationStrategyName,
    StrategyCandidateGenerator,
)
from ai_doc.optimizer.invariants import Invariant, extract_invariants, verify_invariants
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_optimizer_preserves_critical_invariants(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST run validation.\n"
        "- NEVER modify generated files.\n"
        "- Duplicate useful route.\n"
        "- Duplicate useful route.\n",
        encoding="utf-8",
    )
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(snapshot)
    _, rendered = ConservativeCandidateGenerator().generate(snapshot, invariants)
    candidate = snapshot.documents[0].model_copy(update={"text": rendered["AGENTS.md"]})
    assert verify_invariants(invariants, [candidate]) == []


def test_missing_critical_invariant_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\n- MUST run validation.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(snapshot)
    candidate = snapshot.documents[0].model_copy(
        update={"text": "# Rules\n\nValidation is optional.\n"}
    )
    assert verify_invariants(invariants, [candidate]) == ["inv-1"]


class FakeGenerationStrategy:
    name = GenerationStrategyName.CLARITY

    def generate(
        self,
        snapshot: DocumentationSnapshot,
        invariants: list[Invariant],
    ) -> tuple[CandidateProposal, dict[str, str]]:
        del snapshot, invariants
        return (
            CandidateProposal(
                operations=[
                    ProposalOperation(
                        type="retain",
                        reason="fake strategy",
                        expected_clarity_effect="none",
                        expected_finops_effect="none",
                        risk="low",
                    )
                ]
            ),
            {"AGENTS.md": "# Fake\n"},
        )


def test_strategy_candidate_generator_uses_registered_strategy(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse best practices.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())

    proposal, rendered = StrategyCandidateGenerator(
        strategies={GenerationStrategyName.CLARITY: FakeGenerationStrategy()}
    ).generate(snapshot, [], GenerationStrategyName.CLARITY)

    assert proposal.operations[0].reason == "fake strategy"
    assert rendered == {"AGENTS.md": "# Fake\n"}
