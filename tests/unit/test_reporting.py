from __future__ import annotations

from ai_doc.domain.findings import Finding
from ai_doc.domain.optimization import Candidate, ObjectiveVector, OptimizationRun, ParetoArchive, ParetoEntry
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.domain.scores import ContextCost, ScoreSet
from ai_doc.reporting.console import render_check_console, render_search_optimize_console
from ai_doc.reporting.models import CheckReport, SearchOptimizeReport, score_from_report


def _report(tokens: int, findings: list[Finding] | None = None) -> CheckReport:
    return CheckReport(
        files_analyzed=1,
        total_tokens=tokens,
        token_counter="approximate",
        context_cost=ContextCost(
            raw_tokens=tokens,
            always_loaded_tokens=tokens,
            referenced_tokens=0,
            duplicate_tokens=3,
        ),
        profiles={"AGENTS.md": "instruction"},
        findings=findings or [],
    )


class CustomScoringStrategy:
    def score(self, report: CheckReport) -> ScoreSet:
        return ScoreSet(
            clarity_errors=0,
            clarity_warnings=0,
            finops_warnings=0,
            structure_errors=0,
            total_tokens=report.total_tokens + 10,
            always_loaded_tokens=report.context_cost.always_loaded_tokens,
            duplicate_tokens=report.context_cost.duplicate_tokens,
        )


def test_score_from_report_accepts_custom_strategy() -> None:
    score = score_from_report(_report(100), strategy=CustomScoringStrategy())

    assert score.total_tokens == 110


def test_render_check_console_reports_summary_and_top_findings() -> None:
    finding = Finding(
        code="CLARITY_PASSIVE",
        category="clarity",
        severity="warning",
        path="AGENTS.md",
        section="Rules",
        message="Passive wording found.",
        evidence={},
        suggestion="Use direct instructions.",
    )

    output = render_check_console(_report(100, [finding]))

    assert "Files analyzed: 1" in output
    assert "Warnings: 1" in output
    assert "[CLARITY:WARNING] AGENTS.md#Rules" in output
    assert "Suggestion: Use direct instructions." in output


def test_render_search_optimize_console_reports_baseline_and_frontier() -> None:
    baseline_vector = ObjectiveVector(
        reliability=1.0,
        clarity=0.9,
        always_loaded_tokens=100,
        critical_invariant_recall=1.0,
    )
    candidate_vector = ObjectiveVector(
        reliability=1.0,
        clarity=0.95,
        always_loaded_tokens=80,
        critical_invariant_recall=1.0,
    )
    baseline = Candidate(
        id="baseline",
        strategy="baseline",
        proposal=CandidateProposal(operations=[]),
        objective_vector=baseline_vector,
        generation=0,
    )
    frontier_entry = ParetoEntry(
        candidate_id="C001",
        objective_vector=candidate_vector,
        generation=1,
        proposal_summary=["Trim duplicated setup notes"],
    )

    output = render_search_optimize_console(
        SearchOptimizeReport(
            baseline=_report(100),
            run=OptimizationRun(
                run_id="run-1",
                strategy="balanced",
                candidates=[baseline],
                frontier=ParetoArchive(entries=[frontier_entry]),
                recommended_candidate_id="C001",
                stopped_reason="complete",
            ),
            candidates_evaluated=1,
            candidates_rejected=0,
            frontier=[frontier_entry],
            recommended_candidate=None,
            baseline_in_frontier=False,
        )
    )

    assert "always-loaded:       100 tokens" in output
    assert "C001 - Trim duplicated setup notes" in output
    assert "Recommended:\n  C001" in output
