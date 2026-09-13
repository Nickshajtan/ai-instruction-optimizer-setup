from __future__ import annotations

from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.analyzers.semantic_contradiction import SemanticContradictionAnalyzer
from ai_doc.analyzers.semantic_duplication import SemanticDuplicationAnalyzer
from ai_doc.config.models import DEFAULT_CONFIG, LocalMLConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.ml.base import NLIRelation, NLIResult
from ai_doc.tokens.counter import ApproximateTokenCounter


class FakeSimilarityEngine:
    def __init__(self, similarity: float) -> None:
        self.similarity_value = similarity
        self.calls = 0

    def similarity(self, _left: str, _right: str) -> float:
        self.calls += 1
        return self.similarity_value


class FakeNLIEngine:
    def __init__(self, results: list[NLIResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def classify(self, _premise: str, _hypothesis: str) -> NLIResult:
        self.calls += 1
        if not self.results:
            raise AssertionError("Unexpected NLI call")
        return self.results.pop(0)


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


def _write_duplicate_fixture(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Run PHPUnit for every changed PHP module.\n- PHP module changes must be covered by PHPUnit.\n",
        encoding="utf-8",
    )


def test_semantic_duplicate_is_probable_when_similarity_is_high_but_nli_is_not_equivalent(tmp_path: Path) -> None:
    _write_duplicate_fixture(tmp_path)
    nli = FakeNLIEngine(
        [
            NLIResult(relation=NLIRelation.ENTAILMENT, confidence=0.97),
            NLIResult(relation=NLIRelation.NEUTRAL, confidence=0.96),
        ]
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.96), nli).analyze(_context(tmp_path))
    matches = [item for item in findings if item.code == "FINOPS_SEMANTIC_DUPLICATE"]
    assert len(matches) == 1
    assert matches[0].evidence["evidence_level"] == "probable_similarity"
    assert nli.calls == 2


def test_bidirectional_entailment_reports_strong_semantic_duplicate(tmp_path: Path) -> None:
    _write_duplicate_fixture(tmp_path)
    nli = FakeNLIEngine(
        [
            NLIResult(relation=NLIRelation.ENTAILMENT, confidence=0.97),
            NLIResult(relation=NLIRelation.ENTAILMENT, confidence=0.95),
        ]
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.96), nli).analyze(_context(tmp_path))
    matches = [item for item in findings if item.code == "FINOPS_STRONG_SEMANTIC_DUPLICATE"]
    assert len(matches) == 1
    assert matches[0].evidence["evidence_level"] == "strong_bidirectional_entailment"
    assert matches[0].evidence["left_entails_right"]["relation"] == "entailment"
    assert matches[0].evidence["right_entails_left"]["relation"] == "entailment"


def test_one_way_entailment_is_not_strong_duplicate(tmp_path: Path) -> None:
    _write_duplicate_fixture(tmp_path)
    nli = FakeNLIEngine(
        [
            NLIResult(relation=NLIRelation.ENTAILMENT, confidence=0.97),
            NLIResult(relation=NLIRelation.NEUTRAL, confidence=0.98),
        ]
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.96), nli).analyze(_context(tmp_path))
    codes = {item.code for item in findings}
    assert "FINOPS_STRONG_SEMANTIC_DUPLICATE" not in codes
    assert "FINOPS_SEMANTIC_DUPLICATE" in codes


def test_contradiction_is_not_a_duplicate(tmp_path: Path) -> None:
    _write_duplicate_fixture(tmp_path)
    nli = FakeNLIEngine(
        [
            NLIResult(relation=NLIRelation.CONTRADICTION, confidence=0.99),
            NLIResult(relation=NLIRelation.CONTRADICTION, confidence=0.99),
        ]
    )
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.98), nli).analyze(_context(tmp_path))
    codes = {item.code for item in findings}
    assert "FINOPS_STRONG_SEMANTIC_DUPLICATE" not in codes
    assert "FINOPS_SEMANTIC_DUPLICATE" not in codes


def test_below_similarity_threshold_does_not_call_nli(tmp_path: Path) -> None:
    _write_duplicate_fixture(tmp_path)
    nli = FakeNLIEngine([])
    findings = SemanticDuplicationAnalyzer(FakeSimilarityEngine(0.89), nli).analyze(_context(tmp_path))
    assert "FINOPS_SEMANTIC_DUPLICATE" not in {item.code for item in findings}
    assert nli.calls == 0


def test_nli_contradiction_is_reported_with_injected_engine(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always run validation locally.\n- Required to run validation only in CI.\n",
        encoding="utf-8",
    )
    result = NLIResult(relation=NLIRelation.CONTRADICTION, confidence=0.96)
    findings = SemanticContradictionAnalyzer(FakeNLIEngine([result])).analyze(_context(tmp_path))
    assert "RISK_SEMANTIC_CONTRADICTION" in {item.code for item in findings}


def test_nli_neutral_does_not_report_contradiction(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always run unit tests.\n- Never edit generated files.\n",
        encoding="utf-8",
    )
    result = NLIResult(relation=NLIRelation.NEUTRAL, confidence=0.99)
    findings = SemanticContradictionAnalyzer(FakeNLIEngine([result])).analyze(_context(tmp_path))
    assert "RISK_SEMANTIC_CONTRADICTION" not in {item.code for item in findings}
