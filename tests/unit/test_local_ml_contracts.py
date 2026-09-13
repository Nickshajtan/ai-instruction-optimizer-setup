from ai_doc.ml.base import NLIResult, NLIRelation


def test_nli_result_keeps_relation_and_confidence() -> None:
    result = NLIResult(relation=NLIRelation.CONTRADICTION, confidence=0.95)
    assert result.relation == NLIRelation.CONTRADICTION
    assert result.confidence == 0.95
