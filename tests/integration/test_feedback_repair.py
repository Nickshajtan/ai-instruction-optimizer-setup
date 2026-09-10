from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.optimization import OptimizationFeedback
from ai_doc.optimizer.generator import ConservativeCandidateGenerator, StrategyCandidateGenerator
from ai_doc.optimizer.invariants import extract_invariants
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_feedback_repair_strengthens_router_without_restoring_extraction(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST run validation.\n"
        "- NEVER modify generated files.\n\n"
        "## Testing Examples\n\n"
        + "Example: run the narrow test before broad validation.\n" * 80,
        encoding="utf-8",
    )
    baseline = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    invariants = extract_invariants(baseline)
    _, parent_rendered = ConservativeCandidateGenerator().generate(baseline, invariants)
    parent_root = tmp_path / "parent"
    for relative, text in parent_rendered.items():
        target = parent_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    parent_snapshot = discover_markdown(parent_root, DEFAULT_CONFIG, ApproximateTokenCounter())
    feedback = OptimizationFeedback(
        candidate_id="C001",
        weaknesses=["testing router no longer clearly tells the agent when docs/testing.md must be loaded"],
        suggested_mutation_directions=["Retain extraction, but strengthen the root router trigger."],
    )
    _, child_rendered = StrategyCandidateGenerator().generate(
        parent_snapshot,
        invariants,
        "balanced",
        feedback=feedback,
    )
    assert "docs/ai-doc-extracted/AGENTS-testing-examples.md" in child_rendered
    assert "MUST read [Testing Examples]" in child_rendered["AGENTS.md"]
    assert child_rendered["AGENTS.md"].count("Example: run the narrow test") == 0
