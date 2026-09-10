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
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite, Evaluator
from ai_doc.domain.optimization import (
    Candidate,
    CandidateCost,
    CandidateStatus,
    OptimizationRun,
    SearchMemory,
    StopReason,
    failed_cases,
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
from ai_doc.optimizer.evaluation import fingerprint_candidate, hard_constraint_failures, objective_from_report
from ai_doc.optimizer.feedback import FeedbackBuilder, update_search_memory
from ai_doc.optimizer.generator import GenerationStrategyName, SemanticCandidateGenerator, StrategyCandidateGenerator
from ai_doc.optimizer.invariants import (
    Invariant,
    InvariantImportance,
    SemanticInvariantVerifier,
    extract_invariants,
    verify_invariants_with_semantics,
)
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
GEPA_METADATA_KEY = "gepa"
BASELINE_IN_FRONTIER_METADATA_KEY = "baseline_in_frontier"
SEMANTIC_EVALUATION_METADATA_KEY = "semantic_evaluation"
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
        evaluator: Evaluator | None = None,
        semantic_generator: SemanticCandidateGenerator | None = None,
        semantic_invariant_verifier: SemanticInvariantVerifier | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime
        self.output_root = output_root
        self.generator = StrategyCandidateGenerator(semantic=semantic_generator)
        self.selector = ParetoSelector(runtime.pareto)
        self.archive_builder = ParetoArchiveBuilder(self.selector)
        self.recommendation = RecommendationPolicy(runtime.recommendation)
        self.random = random.Random(runtime.seed)
        self.extensions = extensions
        self.evaluator = evaluator
        self.semantic_invariant_verifier = semantic_invariant_verifier

    def optimize(
        self, baseline: DocumentationSnapshot, suite: EvaluationSuite, baseline_report: CheckReport
    ) -> SearchResult:
        run_dir = create_run_dir(self.output_root)
        write_snapshot_tree(baseline, run_dir / BASELINE_TREE_DIR)
        invariants = extract_invariants(baseline)
        critical_count = sum(1 for invariant in invariants if invariant.importance == InvariantImportance.CRITICAL)
        baseline_evaluation, baseline_eval_requests = self._semantic_evaluate(baseline, None, suite)
        baseline_candidate = self._baseline_candidate(
            baseline_report, critical_count, baseline_evaluation, baseline_eval_requests
        )
        candidates: list[Candidate] = [baseline_candidate]
        reports: dict[str, CheckReport] = {BASELINE_CANDIDATE_ID: baseline_report}
        fingerprints: set[str] = set()
        memory = SearchMemory()
        stop_reason = StopReason.GENERATION_COMPLETE
        generation = 1
        generated_count = 0
        no_frontier_entries = 0

        while generation <= self._max_generations():
            batch_strategies = (
                self._initial_strategies()
                if generation == 1
                else [GenerationStrategyName.BALANCED] * self.runtime.search.children_per_generation
            )
            parents = [baseline_candidate for _ in batch_strategies]
            if generation > 1:
                parents = self._select_repair_or_frontier_parents(candidates, len(batch_strategies))
            generation_entered = False
            for index, strategy in enumerate(batch_strategies):
                if generated_count >= self.runtime.search.max_candidates:
                    stop_reason = StopReason.CANDIDATE_BUDGET
                    break
                estimated_requests = self._estimated_external_requests(strategy, suite)
                if self._request_budget_exhausted(candidates, estimated_requests):
                    stop_reason = StopReason.REQUEST_BUDGET
                    break
                if self._cost_budget_exhausted(candidates):
                    stop_reason = StopReason.COST_BUDGET
                    break
                parent = parents[index] if index < len(parents) else baseline_candidate
                feedback = None
                if generation > 1 and parent.id in reports:
                    feedback = FeedbackBuilder().build(
                        parent, baseline_report, reports[parent.id], self.selector.frontier(candidates)
                    )
                source_snapshot = self._source_snapshot(parent, baseline)
                candidate_id = f"{CANDIDATE_ID_PREFIX}{generated_count + 1:0{CANDIDATE_ID_WIDTH}d}"
                proposal, rendered = self.generator.generate(
                    source_snapshot,
                    invariants,
                    strategy,
                    previous_summaries=[self._candidate_summary(candidate) for candidate in candidates],
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
                    suite,
                    baseline_report,
                    invariants,
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
                GEPA_METADATA_KEY: {
                    **self.runtime.gepa.model_dump(),
                    "performed": False,
                    "reason": "no eligible prompt artifact is wired" if self.runtime.gepa.enabled else "disabled",
                },
                BASELINE_IN_FRONTIER_METADATA_KEY: any(item.id == BASELINE_CANDIDATE_ID for item in frontier),
                SEMANTIC_EVALUATION_METADATA_KEY: self.evaluator is not None,
            },
        )
        return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=reports)

    def _baseline_candidate(
        self, report: CheckReport, critical_count: int, evaluation: EvaluationResult | None, evaluation_requests: int
    ) -> Candidate:
        return Candidate(
            id=BASELINE_CANDIDATE_ID,
            strategy=BASELINE_CANDIDATE_ID,
            proposal=CandidateProposal(operations=[]),
            objective_vector=objective_from_report(report, [], critical_count, evaluation),
            evaluation=evaluation,
            status=CandidateStatus.FRONTIER,
            generation=0,
            creation_cost=CandidateCost(evaluation_requests=evaluation_requests),
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
        suite: EvaluationSuite,
        baseline_report: CheckReport,
        invariants: list[Invariant],
        critical_count: int,
        fingerprints: set[str],
        run_dir: Path,
    ) -> tuple[Candidate, CheckReport]:
        candidate_dir = run_dir / CANDIDATES_DIR / candidate_id
        candidate_dir.mkdir(parents=True)
        write_proposal(proposal, candidate_dir)
        tree = write_candidate_tree(source_snapshot, rendered, candidate_dir)
        copy_untracked_context(baseline.root, tree)
        diff_path = write_diff(source_snapshot, rendered, candidate_dir)
        report = run_static_check(tree, self.config, extensions=self.extensions)
        snapshot = discover_markdown(tree, self.config, ApproximateTokenCounter())
        invariant_regressions = verify_invariants_with_semantics(invariants, snapshot, self.semantic_invariant_verifier)
        operation_types = [operation.type for operation in proposal.operations]
        fingerprint = fingerprint_candidate(rendered, operation_types)
        duplicate = fingerprint.content_hash in fingerprints
        fingerprints.add(fingerprint.content_hash)
        tier0_failures = hard_constraint_failures(report, invariant_regressions, None, baseline_report)
        evaluation: EvaluationResult | None = None
        evaluation_requests = 0
        if not tier0_failures and not duplicate:
            evaluation, evaluation_requests = self._semantic_evaluate(baseline, snapshot, suite)
        failures = hard_constraint_failures(report, invariant_regressions, evaluation, baseline_report)
        if duplicate:
            failures.append(DUPLICATE_FINGERPRINT_FAILURE)
        objective = objective_from_report(report, invariant_regressions, critical_count, evaluation)
        generation_requests = int(
            self.generator.semantic is not None
            and _strategy_name_for_cost(strategy) != GenerationStrategyName.CONSERVATIVE
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
            creation_cost=CandidateCost(
                deterministic_operations=len(proposal.operations),
                generation_requests=generation_requests,
                evaluation_requests=evaluation_requests,
            ),
            fingerprint=fingerprint,
            rejection_reasons=failures,
            artifact_dir=str(candidate_dir),
        )
        evidence = evaluation or EvaluationResult(
            engine="tier0-static", passed=not failures, raw_summary={"diff": str(diff_path), "semantic": False}
        )
        (candidate_dir / EVALUATION_ARTIFACT).write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
        return candidate, report

    def _semantic_evaluate(
        self, baseline: DocumentationSnapshot, candidate: DocumentationSnapshot | None, suite: EvaluationSuite
    ) -> tuple[EvaluationResult | None, int]:
        if self.evaluator is None or not suite.scenarios:
            return None, 0
        return self.evaluator.evaluate(baseline, candidate, suite), len(suite.scenarios)

    def _initial_strategies(self) -> list[GenerationStrategyName]:
        if self.runtime.mode == OptimizeMode.CONSERVATIVE:
            return [GenerationStrategyName.CONSERVATIVE]
        base = [
            GenerationStrategyName.CONSERVATIVE,
            GenerationStrategyName.CLARITY,
            GenerationStrategyName.FINOPS,
            GenerationStrategyName.BALANCED,
        ]
        return [base[index % len(base)] for index in range(self.runtime.population.initial_candidates)]

    def _source_snapshot(self, parent: Candidate, baseline: DocumentationSnapshot) -> DocumentationSnapshot:
        if parent.id == BASELINE_CANDIDATE_ID or not parent.artifact_dir:
            return baseline
        candidate_root = Path(parent.artifact_dir) / CANDIDATE_TREE_DIR
        return (
            discover_markdown(candidate_root, self.config, ApproximateTokenCounter())
            if candidate_root.exists()
            else baseline
        )

    def _max_generations(self) -> int:
        return 1 if self.runtime.mode != OptimizeMode.SEARCH else self.runtime.search.generations

    def _select_repair_or_frontier_parents(self, candidates: list[Candidate], count: int) -> list[Candidate]:
        repairable = sorted(
            (candidate for candidate in candidates if candidate.artifact_dir and failed_cases(candidate.evaluation)),
            key=lambda candidate: candidate.id,
        )
        pool = repairable or self.selector.frontier(candidates)
        if not pool:
            return []
        return [self.random.choice(pool) for _ in range(count)]

    def _candidate_summary(self, candidate: Candidate) -> str:
        operations = ",".join(operation.type for operation in candidate.proposal.operations) or "baseline"
        return f"{candidate.id}:{candidate.status.value}:{operations}"

    def _estimated_external_requests(self, strategy: GenerationStrategyName, suite: EvaluationSuite) -> int:
        generation_requests = int(
            self.generator.semantic is not None and strategy != GenerationStrategyName.CONSERVATIVE
        )
        evaluation_requests = len(suite.scenarios) if self.evaluator is not None else 0
        return generation_requests + evaluation_requests

    def _request_budget_exhausted(self, candidates: list[Candidate], next_requests: int = 0) -> bool:
        used = sum(candidate.creation_cost.external_requests for candidate in candidates)
        return used + next_requests > self.runtime.search.max_llm_requests

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
            deterministic_operations=sum(candidate.creation_cost.deterministic_operations for candidate in candidates),
            generation_requests=sum(candidate.creation_cost.generation_requests for candidate in candidates),
            evaluation_requests=sum(candidate.creation_cost.evaluation_requests for candidate in candidates),
            prompt_suboptimizer_requests=sum(
                candidate.creation_cost.prompt_suboptimizer_requests for candidate in candidates
            ),
            total_cost=sum(
                (
                    candidate.creation_cost.total_cost
                    for candidate in candidates
                    if candidate.creation_cost.total_cost is not None
                ),
                Decimal("0"),
            ),
        )


def _strategy_name_for_cost(strategy: str) -> GenerationStrategyName:
    try:
        return GenerationStrategyName(strategy)
    except ValueError:
        return GenerationStrategyName.CONSERVATIVE
