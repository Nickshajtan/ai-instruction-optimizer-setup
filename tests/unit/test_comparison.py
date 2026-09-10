from ai_doc.domain.findings import Finding
from ai_doc.domain.scores import ContextCost
from ai_doc.optimizer.selector import compare_candidates
from ai_doc.reporting.models import CheckReport


def _report(tokens: int, findings: list[Finding] | None = None) -> CheckReport:
    return CheckReport(
        files_analyzed=1,
        total_tokens=tokens,
        token_counter="approximate",
        context_cost=ContextCost(
            raw_tokens=tokens, always_loaded_tokens=tokens, referenced_tokens=0, duplicate_tokens=0
        ),
        profiles={"AGENTS.md": "instruction"},
        findings=findings or [],
    )


def test_comparison_rejects_invariant_regression() -> None:
    comparison = compare_candidates(_report(100), _report(50), ["inv-1"], None)
    assert comparison.recommendation == "reject"
