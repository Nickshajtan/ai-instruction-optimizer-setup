from __future__ import annotations

from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.analyzers.semantic_contradiction import SemanticContradictionAnalyzer
from ai_doc.analyzers.semantic_duplication import SemanticDuplicationAnalyzer
from ai_doc.config.models import DEFAULT_CONFIG, LocalMLConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.ml.base import NLIResult, NLIRelation
from ai_doc.tokens.counter import ApproximateTokenCounter


class FakeSimilarityEngine:
    def __init__(self, similarity: float) -> None:
        self.similarity_value = similarity

    def similarity(self, _left: str, _right: str) -> float:
        return self.similarity_value


class FakeNLIEngine:
    def __init__(self, result: NLIResult) -> None:
        self.result = result

    def classify(self, _premise: str, _hypothesis: str) -> NLIResult:
        return self.result


def _context(tmp_path: Path, *, similarity_threshold: float = 0.90, nli_threshold: float = 0.90) -> AnalysisContext:
    config = DEFAULT_CONFIG.model_copy(
        update={
            "local_ml": LocalMLConfig(
                enabled=True,
                similarity_threshold=similarity_threshold,
                nli_confidence_threshold=nli_threshold,
            )
        }
    )
    snapshot = discover_markdown(tmp_path, config, ApproximateTokenCounter())
    return AnalysisContext(config=config, snapshot=snapshot, graph=DocumentGraph(snapshot))


def test_semantic_duplicate_is_reported_with_injected_engine(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Run PHPUnit for every changed PHP module.\n- PHP module changes must be covered by PHPUnit.\n",
        encoding="utf-8",
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.96)).analyze(_context(tmp_path))
    matches = [item for item in findings if item.code == "FINOPS_SEMANTIC_DUPLICATE"]
    assert len(matches) == 1
    assert matches[0].evidence["similarity"] == 0.96


def test_semantic_duplicate_respects_threshold(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Run PHPUnit for every changed PHP module.\n- PHP module changes must be covered by PHPUnit.\n",
        encoding="utf-8",
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.89)).analyze(_context(tmp_path))
    assert "FINOPS_SEMANTIC_DUPLICATE" not in {item.code for item in findings}


def test_nli_contradiction_is_reported_with_injected_engine(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always run validation locally.\n- Required to run validation only in CI.\n",
        encoding="utf-8",
    )
    result = NLIResult(relation=NLIRelation.CONTRADICTION, confidence=0.96)
    findings = SemanticContradictionAnalyzer(FakeNLIEngine(result)).analyze(_context(tmp_path))
    assert "RISK_SEMANTIC_CONTRADICTION" in {item.code for item in findings}


def test_nli_neutral_does_not_report_contradiction(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always run unit tests.\n- Never edit generated files.\n",
        encoding="utf-8",
    )
    result = NLIResult(relation=NLIRelation.NEUTRAL, confidence=0.99)
    findings = SemanticContradictionAnalyzer(FakeNLIEngine(result)).analyze(_context(tmp_path))
    assert "RISK_SEMANTIC_CONTRADICTION" not in {item.code for item in findings}


def test_similarity_signal_does_not_become_contradiction(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Run tests before committing changes.\n- Do not run tests before committing changes.\n",
        encoding="utf-8",
    )
    duplication = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.99)).analyze(_context(tmp_path))
    assert "FINOPS_SEMANTIC_DUPLICATE" in {item.code for item in duplication}
    assert "RISK_SEMANTIC_CONTRADICTION" not in {item.code for item in duplication}
