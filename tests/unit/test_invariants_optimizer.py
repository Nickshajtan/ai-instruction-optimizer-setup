from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.optimization import SearchMemory
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
from ai_doc.optimizer.generator import (
    ConservativeCandidateGenerator,
    GenerationStrategyName,
    StrategyCandidateGenerator,
)
from ai_doc.optimizer.invariants import (
    Invariant,
    InvariantSemanticStatus,
    extract_invariants,
    verify_invariants,
    verify_invariants_with_evidence,
    verify_invariants_with_semantics,
)
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
    candidate = snapshot.documents[0].model_copy(update={"text": "# Rules\n\nValidation is optional.\n"})
    assert verify_invariants(invariants, [candidate]) == ["inv-1"]


def test_semantic_verifier_can_accept_meaning_preserving_rewrite(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\n- MUST run validation before completion.\n", encoding="utf-8")
    baseline = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(baseline)
    candidate_doc = baseline.documents[0].model_copy(
        update={"text": "# Rules\n\nCompletion requires validation to be run.\n"}
    )
    candidate = baseline.model_copy(update={"documents": (candidate_doc,)})

    class PreservingVerifier:
        def verify(self, invariant, snapshot):
            assert invariant.id == "inv-1"
            assert snapshot is candidate
            return InvariantSemanticStatus.PRESERVED

    assert verify_invariants_with_semantics(invariants, candidate, PreservingVerifier()) == []


def test_semantic_verifier_rejects_weakened_invariant(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\n- MUST run validation before completion.\n", encoding="utf-8")
    baseline = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(baseline)
    candidate_doc = baseline.documents[0].model_copy(update={"text": "# Rules\n\nValidation is recommended.\n"})
    candidate = baseline.model_copy(update={"documents": (candidate_doc,)})

    class WeakeningVerifier:
        def verify(self, invariant, snapshot):
            return InvariantSemanticStatus.WEAKENED

    assert verify_invariants_with_semantics(invariants, candidate, WeakeningVerifier()) == ["inv-1"]


def test_literal_critical_wording_does_not_bypass_semantic_contradiction_check(tmp_path: Path) -> None:
    original = "MUST run validation before merge."
    (tmp_path / "AGENTS.md").write_text(f"# Rules\n\n{original}\n", encoding="utf-8")
    baseline = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(baseline)
    contradictory = (
        f"# Rules\n\n{original}\n\n"
        "For migration-only changes, validation is optional and may be skipped.\n"
    )
    candidate_doc = baseline.documents[0].model_copy(update={"text": contradictory})
    candidate = baseline.model_copy(update={"documents": (candidate_doc,)})
    calls = 0

    class ContradictionVerifier:
        def verify(self, invariant, snapshot):
            nonlocal calls
            calls += 1
            assert invariant.text == original
            assert "may be skipped" in snapshot.documents[0].text
            return InvariantSemanticStatus.UNCERTAIN

    unsafe, decisions = verify_invariants_with_evidence(invariants, candidate, ContradictionVerifier())
    assert calls == 1
    assert unsafe == ["inv-1"]
    assert decisions[0].status == "uncertain"
    assert decisions[0].source == "literal+semantic"


class FakeGenerationStrategy:
    name = GenerationStrategyName.CLARITY

    def generate(
        self, snapshot: DocumentationSnapshot, invariants: list[Invariant]
    ) -> tuple[CandidateProposal, dict[str, str]]:
        del snapshot, invariants
        return CandidateProposal(
            operations=[
                ProposalOperation(
                    type="retain",
                    reason="fake strategy",
                    expected_clarity_effect="none",
                    expected_finops_effect="none",
                    risk="low",
                )
            ]
        ), {"AGENTS.md": "# Fake\n"}


def test_strategy_candidate_generator_uses_registered_strategy(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse best practices.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    proposal, rendered = StrategyCandidateGenerator(
        strategies={GenerationStrategyName.CLARITY: FakeGenerationStrategy()}
    ).generate(snapshot, [], GenerationStrategyName.CLARITY)
    assert proposal.operations[0].reason == "fake strategy"
    assert rendered == {"AGENTS.md": "# Fake\n"}


def test_semantic_generator_receives_search_state(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nUse best practices.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    captured: dict[str, object] = {}

    class FakeSemanticGenerator:
        def generate(
            self, snapshot, invariants, strategy, previous_summaries, explored_transformations, feedback, memory
        ):
            captured.update(
                {
                    "strategy": strategy,
                    "summaries": previous_summaries,
                    "explored": explored_transformations,
                    "memory": memory,
                }
            )
            return CandidateProposal(
                operations=[
                    ProposalOperation(
                        type="rewrite",
                        target="AGENTS.md",
                        reason="semantic fake",
                        expected_clarity_effect="better",
                        expected_finops_effect="same",
                        risk="low",
                    )
                ]
            ), {"AGENTS.md": "# Semantic\n"}

    memory = SearchMemory(unexplored_opportunities=["strengthen router"])
    proposal, rendered = StrategyCandidateGenerator(semantic=FakeSemanticGenerator()).generate(
        snapshot,
        [],
        GenerationStrategyName.BALANCED,
        previous_summaries=["C001:rejected:extract"],
        explored_transformations=["abc"],
        memory=memory,
    )
    assert proposal.operations[0].reason == "semantic fake"
    assert rendered["AGENTS.md"] == "# Semantic\n"
    assert captured["summaries"] == ["C001:rejected:extract"]
    assert captured["explored"] == ["abc"]
    assert captured["memory"] == memory
