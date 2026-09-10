from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import AiDocConfig
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.domain.optimization import (
    Candidate,
    CandidateCost,
    CandidateStatus,
    OptimizationRun,
    SearchMemory,
    StopReason,
)
from ai_doc.domain.proposals import CandidateProposal
from ai_doc.optimizer.candidate import (
    copy_untracked_context,
    create_run_dir,
    write_candidate_tree,
    write_diff,
    write_proposal,
    write_snapshot_tree,
)
from ai_doc.optimizer.evaluation import (
    fingerprint_candidate,
    hard_constraint_failures,
    objective_from_report,
)
from ai_doc.optimizer.feedback import FeedbackBuilder, update_search_memory
from ai_doc.optimizer.generator import GenerationStrategyName, StrategyCandidateGenerator
from ai_doc.optimizer.invariants import InvariantImportance, extract_invariants, verify_invariants
from ai_doc.optimizer.pareto import ParetoArchiveBuilder, ParetoSelector
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.reporting.models import CheckReport
from ai_doc.tokens.counter import ApproximateTokenCounter

BASELINE_CANDIDATE_ID = "baseline"
BASELINE_TREE_DIR = "baseline"
CANDIDATE_ID_PREFIX = "C"
CANDIDATE_ID_WIDTH = 3
CANDIDATES_DIR = "candidates"
CANDIDATE_TREE_DIR = "candidate"
EVALUATION_ARTIFACT = "evaluation.json"
TIER0_STATIC_ENGINE = "tier0-static"
TIER0_STATIC_TIER = 0
DIFF_METADATA_KEY = "diff"
TIER_METADATA_KEY = "tier"
GEPA_METADATA_KEY = "gepa"
BASELINE_IN_FRONTIER_METADATA_KEY = "baseline_in_frontier"
DUPLICATE_FINGERPRINT_FAILURE = "duplicate candidate fingerprint"


@dataclass
class SearchResult:
    run: OptimizationRun
    run_dir: Path
    baseline_report: CheckReport
    reports: dict[str, CheckReport]


class SearchController:
    def __init__(
        self,
        config: AiDocConfig,
        runtime: RuntimeSearchConfig,
        output_root: Path,
        extensions: ExtensionRegistry | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime
        self.output_root = output_root
        self.generator = StrategyCandidateGenerator()
        self.selector = ParetoSelector(runtime.pareto)
        self.archive_builder = ParetoArchiveBuilder(self.selector)
        self.recommendation = RecommendationPolicy(runtime.recommendation)
        self.random = random.Random(runtime.seed)
        self.extensions = extensions

    def optimize(
        self,
        baseline: DocumentationSnapshot,
        suite: EvaluationSuite,
        baseline_report: CheckReport,
    ) -> SearchResult:
        del suite
        run_dir = create_run_dir(self.output_root)
        write_snapshot_tree(baseline, run_dir / BASELINE_TREE_DIR)
        invariants = extract_invariants(baseline)
        critical_count = sum(1 for invariant in invariants if invariant.importance == InvariantImportance.CRITICAL)
        baseline_candidate = self._baseline_candidate(baseline_report, critical_count)
        candidates: list[Candidate] = [baseline_candidate]
        reports: dict[str, CheckReport] = {BASELINE_CANDIDATE_ID: baseline_report}
        fingerprints: set[str] = set()
        memory = SearchMemory()
        stop_reason = StopReason.GENERATION_COMPLETE

        generation = 1
        generated_count = 0
        no_frontier_entries = 0
        while generation <= self._max_generations():
            batch_strategies = self._initial_strategies() if generation == 1 else [
                GenerationStrategyName.BALANCED
            ] * self.runtime.search.children_per_generation
            parents = [baseline_candidate for _ in batch_strategies]
            if generation > 1:
                parents = self._select_parents(self.selector.frontier(candidates), len(batch_strategies))
            generation_entered = False
            for index, strategy in enumerate(batch_strategies):
                if generated_count >= self.runtime.search.max_candidates:
                    stop_reason = StopReason.CANDIDATE_BUDGET
                    break
                if self._request_budget_exhausted(candidates):
                    stop_reason = StopReason.REQUEST_BUDGET
                    break
                if self._cost_budget_exhausted(candidates):
                    stop_reason = StopReason.COST_BUDGET
                    break
                parent = parents[index] if index < len(parents) else baseline_candidate
                feedback = None
                if generation > 1 and parent.id in reports:
                    feedback = FeedbackBuilder().build(
                        parent,
                        baseline_report,
                        reports[parent.id],
                        self.selector.frontier(candidates),
                    )
                source_snapshot = self._source_snapshot(parent, baseline)
                candidate_id = f"{CANDIDATE_ID_PREFIX}{generated_count + 1:0{CANDIDATE_ID_WIDTH}d}"
                proposal, rendered = self.generator.generate(
                    source_snapshot,
                    invariants,
                    strategy,
                    previous_summaries=[candidate.id for candidate in candidates],
                    explored_transformations=sorted(fingerprints),
                    feedback=feedback,
                    memory=memory,
                )
                candidate, report = self._evaluate_candidate(
                    candidate_id,
                    generation,
                    parent,
                    strategy,
                    proposal,
                    rendered,
                    source_snapshot,
                    baseline,
                    baseline_report,
                    critical_count,
                    fingerprints,
                    run_dir,
                )
                candidates.append(candidate)
                reports[candidate.id] = report
                generated_count += 1
                frontier = self.selector.frontier(candidates)
                frontier_ids = {item.id for item in frontier}
                if candidate.id in frontier_ids and candidate.status != CandidateStatus.REJECTED:
                    generation_entered = True
                for item in candidates:
                    if item.status != CandidateStatus.REJECTED:
                        item.status = CandidateStatus.FRONTIER if item.id in frontier_ids else CandidateStatus.DOMINATED
                if feedback:
                    memory = update_search_memory(memory, feedback, candidate.id in frontier_ids)
            if stop_reason != StopReason.GENERATION_COMPLETE:
                break
            no_frontier_entries = 0 if generation_entered else no_frontier_entries + 1
            if self.runtime.search.patience and no_frontier_entries >= self.runtime.search.patience:
                stop_reason = StopReason.PATIENCE
                break
            generation += 1

        frontier = self.selector.frontier(candidates)
        for item in candidates:
            if item.status != CandidateStatus.REJECTED:
                item.status = CandidateStatus.FRONTIER if item in frontier else CandidateStatus.DOMINATED
        recommended = self.recommendation.choose(baseline_candidate, frontier)
        run = OptimizationRun(
            run_id=run_dir.name,
            strategy=self.runtime.mode.value,
            seed=self.runtime.seed,
            candidates=candidates,
            frontier=self.archive_builder.build(candidates),
            recommended_candidate_id=recommended.id if recommended else None,
            search_memory=memory,
            stopped_reason=stop_reason,
            total_cost=self._total_cost(candidates),
            metadata={
                GEPA_METADATA_KEY: self.runtime.gepa.model_dump(),
                BASELINE_IN_FRONTIER_METADATA_KEY: any(item.id == BASELINE_CANDIDATE_ID for item in frontier),
            },
        )
        return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=reports)

    def _baseline_candidate(self, report: CheckReport, critical_count: int) -> Candidate:
        return Candidate(
            id=BASELINE_CANDIDATE_ID,
            strategy=BASELINE_CANDIDATE_ID,
            proposal=CandidateProposal(operations=[]),
            objective_vector=objective_from_report(report, [], critical_count),
            status=CandidateStatus.FRONTIER,
            generation=0,
        )

    def _evaluate_candidate(
        self,
        candidate_id: str,
        generation: int,
        parent: Candidate,
        strategy: str,
        proposal: CandidateProposal,
        rendered: dict[str, str],
        source_snapshot: DocumentationSnapshot,
        baseline: DocumentationSnapshot,
        baseline_report: CheckReport,
        critical_count: int,
        fingerprints: set[str],
        run_dir: Path,
    ) -> tuple[Candidate, CheckReport]:
        candidate_dir = run_dir / CANDIDATES_DIR / candidate_id
        candidate_dir.mkdir(parents=True)
        write_proposal(proposal, candidate_dir)
        tree = write_candidate_tree(source_snapshot, rendered, candidate_dir)
        copy_untracked_context(baseline.root, tree, self.config.include)
        diff_path = write_diff(source_snapshot, rendered, candidate_dir)
        report = run_static_check(tree, self.config, extensions=self.extensions)
        snapshot = discover_markdown(tree, self.config, ApproximateTokenCounter())
        invariant_regressions = verify_invariants(extract_invariants(baseline), list(snapshot.documents))
        operation_types = [operation.type for operation in proposal.operations]
        fingerprint = fingerprint_candidate(rendered, operation_types)
        duplicate = fingerprint.content_hash in fingerprints
        fingerprints.add(fingerprint.content_hash)
        failures = hard_constraint_failures(report, invariant_regressions, None, baseline_report)
        if duplicate:
            failures.append(DUPLICATE_FINGERPRINT_FAILURE)
        objective = objective_from_report(report, invariant_regressions, critical_count)
        evaluation = EvaluationResult(
            engine=TIER0_STATIC_ENGINE,
            passed=not failures,
            raw_summary={DIFF_METADATA_KEY: str(diff_path), TIER_METADATA_KEY: TIER0_STATIC_TIER},
        )
        candidate = Candidate(
            id=candidate_id,
            parent_ids=[parent.id],
            strategy=strategy,
            proposal=proposal,
            objective_vector=objective,
            evaluation=evaluation,
            status=CandidateStatus.REJECTED if failures else CandidateStatus.VALID,
            generation=generation,
            creation_cost=CandidateCost(generation_requests=1, evaluation_requests=1),
            fingerprint=fingerprint,
            rejection_reasons=failures,
            artifact_dir=str(candidate_dir),
        )
        (candidate_dir / EVALUATION_ARTIFACT).write_text(evaluation.model_dump_json(indent=2), encoding="utf-8")
        return candidate, report

    def _initial_strategies(self) -> list[GenerationStrategyName]:
        if self.runtime.mode == OptimizeMode.CONSERVATIVE:
            return [GenerationStrategyName.CONSERVATIVE]
        requested = self.runtime.population.initial_candidates
        base = [
            GenerationStrategyName.CONSERVATIVE,
            GenerationStrategyName.CLARITY,
            GenerationStrategyName.FINOPS,
            GenerationStrategyName.BALANCED,
        ]
        return [base[index % len(base)] for index in range(requested)]

    def _source_snapshot(
        self,
        parent: Candidate,
        baseline: DocumentationSnapshot,
    ) -> DocumentationSnapshot:
        if parent.id == BASELINE_CANDIDATE_ID or not parent.artifact_dir:
            return baseline
        candidate_root = Path(parent.artifact_dir) / CANDIDATE_TREE_DIR
        if not candidate_root.exists():
            return baseline
        return discover_markdown(candidate_root, self.config, ApproximateTokenCounter())

    def _max_generations(self) -> int:
        return 1 if self.runtime.mode != OptimizeMode.SEARCH else self.runtime.search.generations

    def _select_parents(self, frontier: list[Candidate], count: int) -> list[Candidate]:
        if not frontier:
            return []
        ordered = sorted(frontier, key=lambda candidate: candidate.id)
        return [self.random.choice(ordered) for _ in range(count)]

    def _request_budget_exhausted(self, candidates: list[Candidate]) -> bool:
        used = sum(candidate.creation_cost.generation_requests for candidate in candidates)
        return used >= self.runtime.search.max_llm_requests

    def _cost_budget_exhausted(self, candidates: list[Candidate]) -> bool:
        if self.runtime.search.max_cost_usd is None:
            return False
        total = sum(
            (
                candidate.creation_cost.total_cost
                for candidate in candidates
                if candidate.creation_cost.total_cost is not None
            ),
            Decimal("0"),
        )
        return total >= self.runtime.search.max_cost_usd

    def _total_cost(self, candidates: list[Candidate]) -> CandidateCost:
        return CandidateCost(
            generation_requests=sum(candidate.creation_cost.generation_requests for candidate in candidates),
            evaluation_requests=sum(candidate.creation_cost.evaluation_requests for candidate in candidates),
            total_cost=sum(
                (
                    candidate.creation_cost.total_cost
                    for candidate in candidates
                    if candidate.creation_cost.total_cost is not None
                ),
                Decimal("0"),
            ),
        )
