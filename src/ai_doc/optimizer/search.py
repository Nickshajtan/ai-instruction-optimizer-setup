from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

from ai_doc.app import run_static_check
from ai_doc.config.models import AiDocConfig
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite, Evaluator
from ai_doc.domain.optimization import (
    Candidate,
    CandidateCost,
    CandidateEvidence,
    CandidateStatus,
    OptimizationFeedback,
    OptimizationRun,
    SearchMemory,
    StopReason,
    failed_cases,
)
from ai_doc.domain.proposals import CandidateProposal, ProposalOperation
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
    SemanticInvariantDiscoverer,
    SemanticInvariantVerifier,
    extract_invariants,
    verify_invariants_with_evidence,
)
from ai_doc.optimizer.pareto import ParetoArchiveBuilder, ParetoSelector
from ai_doc.optimizer.prompt_suboptimizer import PromptArtifact, PromptSubOptimizer
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.providers.semantic import ProviderUsage
from ai_doc.reporting.models import CheckReport
from ai_doc.tokens.counter import ApproximateTokenCounter

BASELINE_CANDIDATE_ID = "baseline"
GEPA_MARKER = "<!-- ai-doc:gepa -->"


@dataclass
class SearchResult:
    run: OptimizationRun
    run_dir: Path
    baseline_report: CheckReport
    reports: dict[str, CheckReport]


class SearchController:  # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        config: AiDocConfig,
        runtime: RuntimeSearchConfig,
        output_root: Path,
        extensions: ExtensionRegistry | None = None,
        evaluator: Evaluator | None = None,
        semantic_generator: SemanticCandidateGenerator | None = None,
        semantic_invariant_verifier: SemanticInvariantVerifier | None = None,
        semantic_invariant_discoverer: SemanticInvariantDiscoverer | None = None,
        prompt_suboptimizer: PromptSubOptimizer | None = None,
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
        self.semantic_invariant_discoverer = semantic_invariant_discoverer
        self.prompt_suboptimizer = prompt_suboptimizer

    def optimize(
        self, baseline: DocumentationSnapshot, suite: EvaluationSuite, baseline_report: CheckReport
    ) -> SearchResult:
        run_dir = create_run_dir(self.output_root)
        write_snapshot_tree(baseline, run_dir / "baseline")
        invariants = extract_invariants(baseline, self.semantic_invariant_discoverer)
        discovery_usage = self._drain_invariant_usage()
        critical_count = sum(item.importance == InvariantImportance.CRITICAL for item in invariants)
        baseline_evaluation, baseline_eval_usage = self._semantic_evaluate(baseline, None, suite)
        baseline_usage = _combine_usage(discovery_usage, baseline_eval_usage)
        baseline_candidate = self._baseline_candidate(
            baseline_report, critical_count, baseline_evaluation, baseline_usage
        )
        candidates = [baseline_candidate]
        reports = {BASELINE_CANDIDATE_ID: baseline_report}
        fingerprints: set[str] = set()
        memory = SearchMemory()
        stop_reason = StopReason.GENERATION_COMPLETE
        generation = 1
        generated_count = 0
        stagnant = 0
        gepa_performed = False

        while generation <= self._max_generations():
            strategies = self._strategies(generation)
            parents = self._parents(generation, strategies, candidates, baseline_candidate)
            entered = False
            for index, strategy in enumerate(strategies):
                if generated_count >= self.runtime.search.max_candidates:
                    stop_reason = StopReason.CANDIDATE_BUDGET
                    break
                if self._budget_exhausted(candidates):
                    stop_reason = self._budget_stop_reason(candidates)
                    break
                parent = parents[index] if index < len(parents) else baseline_candidate
                feedback = self._feedback(generation, parent, reports, baseline_report, candidates)
                source = self._source_snapshot(parent, baseline)
                proposal, rendered = self.generator.generate(
                    source,
                    invariants,
                    strategy,
                    previous_summaries=[self._candidate_summary(item) for item in candidates],
                    explored_transformations=sorted(fingerprints),
                    feedback=feedback,
                    memory=memory,
                )
                generation_usage = self._last_usage(self.generator.semantic)
                gepa_usage = ProviderUsage(requests=0)
                if self.runtime.gepa.enabled:
                    proposal, rendered, gepa_usage, performed = self._apply_gepa(source, proposal, rendered, suite)
                    gepa_performed = gepa_performed or performed
                candidate, report = self._evaluate_candidate(
                    f"C{generated_count + 1:03d}", generation, parent, str(strategy), proposal, rendered, source,
                    baseline, suite, baseline_report, invariants, critical_count, fingerprints, run_dir, feedback,
                    generation_usage, gepa_usage,
                )
                candidates.append(candidate)
                reports[candidate.id] = report
                generated_count += 1
                frontier_ids = {item.id for item in self.selector.frontier(candidates)}
                entered = entered or (candidate.id in frontier_ids and candidate.status != CandidateStatus.REJECTED)
                self._update_statuses(candidates, frontier_ids)
                if feedback:
                    memory = update_search_memory(memory, feedback, candidate.id in frontier_ids)
            if stop_reason != StopReason.GENERATION_COMPLETE:
                break
            stagnant = 0 if entered else stagnant + 1
            if self.runtime.search.patience and stagnant >= self.runtime.search.patience:
                stop_reason = StopReason.PATIENCE
                break
            generation += 1

        frontier = self.selector.frontier(candidates)
        recommended = self.recommendation.choose(baseline_candidate, frontier)
        reason = (
            f"recommended {recommended.id}: non-dominated and policy-qualified"
            if recommended
            else "baseline/no-change retained: no candidate satisfied recommendation policy"
        )
        run = OptimizationRun(
            run_id=run_dir.name,
            strategy=self.runtime.mode.value,
            seed=self.runtime.seed,
            candidates=candidates,
            frontier=self.archive_builder.build(candidates),
            recommended_candidate_id=recommended.id if recommended else None,
            recommendation_reason=reason,
            search_memory=memory,
            stopped_reason=stop_reason,
            total_cost=self._total_cost(candidates),
            metadata={
                "baseline_in_frontier": any(item.id == BASELINE_CANDIDATE_ID for item in frontier),
                "semantic_evaluation": self.evaluator is not None,
                "gepa": {
                    **self.runtime.gepa.model_dump(),
                    "performed": gepa_performed,
                    "reason": self._gepa_reason(gepa_performed),
                },
            },
        )
        return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=reports)

    def _baseline_candidate(
        self, report: CheckReport, critical_count: int, evaluation: EvaluationResult | None, usage: ProviderUsage
    ) -> Candidate:
        return Candidate(
            id=BASELINE_CANDIDATE_ID,
            strategy=BASELINE_CANDIDATE_ID,
            proposal=CandidateProposal(operations=[]),
            objective_vector=objective_from_report(report, [], critical_count, evaluation),
            evaluation=evaluation,
            status=CandidateStatus.FRONTIER,
            generation=0,
            creation_cost=self._evaluation_cost(usage),
            evidence=CandidateEvidence(effective_context=self._effective_context(evaluation)),
        )

    def _evaluate_candidate(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        candidate_id: str,
        generation: int,
        parent: Candidate,
        strategy: str,
        proposal: CandidateProposal,
        rendered: dict[str, str],
        source: DocumentationSnapshot,
        baseline: DocumentationSnapshot,
        suite: EvaluationSuite,
        baseline_report: CheckReport,
        invariants: list[Invariant],
        critical_count: int,
        fingerprints: set[str],
        run_dir: Path,
        feedback: OptimizationFeedback | None,
        generation_usage: ProviderUsage,
        gepa_usage: ProviderUsage,
    ) -> tuple[Candidate, CheckReport]:
        candidate_dir = run_dir / "candidates" / candidate_id
        candidate_dir.mkdir(parents=True)
        write_proposal(proposal, candidate_dir)
        tree = write_candidate_tree(source, rendered, candidate_dir)
        copy_untracked_context(baseline.root, tree)
        diff_path = write_diff(source, rendered, candidate_dir)
        report = run_static_check(tree, self.config, extensions=self.extensions)
        snapshot = discover_markdown(tree, self.config, ApproximateTokenCounter())
        regressions, decisions = verify_invariants_with_evidence(
            invariants, snapshot, self.semantic_invariant_verifier
        )
        invariant_usage = self._drain_invariant_usage()
        fingerprint = fingerprint_candidate(rendered, [operation.type for operation in proposal.operations])
        duplicate = fingerprint.content_hash in fingerprints
        fingerprints.add(fingerprint.content_hash)
        tier0 = hard_constraint_failures(report, regressions, None, baseline_report)
        if tier0 or duplicate or self._would_exceed_after(candidates_cost=None, extra=invariant_usage):
            evaluation = None
            semantic_usage = ProviderUsage(requests=0)
        else:
            evaluation, semantic_usage = self._semantic_evaluate(baseline, snapshot, suite)
        evaluation_usage = _combine_usage(invariant_usage, semantic_usage)
        failures = hard_constraint_failures(report, regressions, evaluation, baseline_report)
        if duplicate:
            failures.append("duplicate candidate fingerprint")
        cost = self._candidate_cost(proposal, generation_usage, evaluation_usage, gepa_usage)
        evidence = CandidateEvidence(
            generation_reason="; ".join(operation.reason for operation in proposal.operations),
            feedback=feedback,
            invariant_decisions=decisions,
            effective_context=self._effective_context(evaluation),
        )
        candidate = Candidate(
            id=candidate_id,
            parent_ids=[parent.id],
            strategy=strategy,
            proposal=proposal,
            objective_vector=objective_from_report(report, regressions, critical_count, evaluation),
            evaluation=evaluation,
            status=CandidateStatus.REJECTED if failures else CandidateStatus.VALID,
            generation=generation,
            creation_cost=cost,
            fingerprint=fingerprint,
            rejection_reasons=failures,
            artifact_dir=str(candidate_dir),
            evidence=evidence,
        )
        eval_evidence = evaluation or EvaluationResult(
            engine="tier0-static",
            passed=not failures,
            raw_summary={"diff": str(diff_path), "semantic": False},
        )
        (candidate_dir / "evaluation.json").write_text(eval_evidence.model_dump_json(indent=2), encoding="utf-8")
        (candidate_dir / "evidence.json").write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
        return candidate, report

    def _apply_gepa(
        self,
        source: DocumentationSnapshot,
        proposal: CandidateProposal,
        rendered: dict[str, str],
        suite: EvaluationSuite,
    ) -> tuple[CandidateProposal, dict[str, str], ProviderUsage, bool]:
        if self.prompt_suboptimizer is None:
            return proposal, rendered, ProviderUsage(requests=0), False
        eligible = next((document for document in source.documents if GEPA_MARKER in document.text), None)
        if eligible is None:
            return proposal, rendered, ProviderUsage(requests=0), False
        current = rendered.get(eligible.relative_path, eligible.text)
        result = self.prompt_suboptimizer.optimize(
            PromptArtifact(id=eligible.relative_path, text=current), suite, self.runtime.search
        )
        usage = self._last_usage(self.prompt_suboptimizer)
        if not result.changed:
            return proposal, rendered, usage, True
        updated = dict(rendered)
        updated[eligible.relative_path] = result.optimized_text
        operation = ProposalOperation(
            type="rewrite",
            target=eligible.relative_path,
            reason="GEPA optimized an explicitly eligible prompt artifact.",
            expected_clarity_effect="Provider-guided prompt improvement.",
            expected_finops_effect="Measured by normal evaluation.",
            risk="medium",
            objective=["reliability"],
        )
        return CandidateProposal(operations=[*proposal.operations, operation]), updated, usage, True

    def _semantic_evaluate(
        self, baseline: DocumentationSnapshot, candidate: DocumentationSnapshot | None, suite: EvaluationSuite
    ) -> tuple[EvaluationResult | None, ProviderUsage]:
        if self.evaluator is None or not suite.scenarios:
            return None, ProviderUsage(requests=0)
        result = self.evaluator.evaluate(baseline, candidate, suite)
        usage = self._last_usage(getattr(self.evaluator, "evaluator", self.evaluator))
        if not usage.requests:
            usage = ProviderUsage(requests=len(suite.scenarios))
        return result, usage

    def _drain_invariant_usage(self) -> ProviderUsage:
        drain = getattr(self.semantic_invariant_verifier, "drain_usage", None)
        if callable(drain):
            usage = drain()
            if isinstance(usage, ProviderUsage):
                return usage
        return ProviderUsage(requests=0)

    def _candidate_cost(
        self,
        proposal: CandidateProposal,
        generation: ProviderUsage,
        evaluation: ProviderUsage,
        gepa: ProviderUsage,
    ) -> CandidateCost:
        return CandidateCost(
            deterministic_operations=len(proposal.operations),
            generation_requests=generation.requests,
            generation_input_tokens=generation.input_tokens,
            generation_output_tokens=generation.output_tokens,
            evaluation_requests=evaluation.requests,
            evaluation_input_tokens=evaluation.input_tokens,
            evaluation_output_tokens=evaluation.output_tokens,
            prompt_suboptimizer_requests=gepa.requests,
            prompt_suboptimizer_input_tokens=gepa.input_tokens,
            prompt_suboptimizer_output_tokens=gepa.output_tokens,
            cache_hits=generation.cache_hits + evaluation.cache_hits + gepa.cache_hits,
            total_cost=generation.cost_usd + evaluation.cost_usd + gepa.cost_usd,
            cost_sources=sorted({item.cost_source for item in (generation, evaluation, gepa) if item.requests}),
        )

    def _strategies(self, generation: int) -> list[GenerationStrategyName]:
        if generation > 1:
            return [GenerationStrategyName.BALANCED] * self.runtime.search.children_per_generation
        if self.runtime.mode == OptimizeMode.CONSERVATIVE:
            return [GenerationStrategyName.CONSERVATIVE]
        base = [
            GenerationStrategyName.CONSERVATIVE,
            GenerationStrategyName.CLARITY,
            GenerationStrategyName.FINOPS,
            GenerationStrategyName.BALANCED,
        ]
        return [base[index % len(base)] for index in range(self.runtime.population.initial_candidates)]

    def _parents(
        self, generation: int, strategies: list[GenerationStrategyName], candidates: list[Candidate], baseline: Candidate
    ) -> list[Candidate]:
        if generation == 1:
            return [baseline] * len(strategies)
        repairable = sorted(
            (candidate for candidate in candidates if candidate.artifact_dir and failed_cases(candidate.evaluation)),
            key=lambda candidate: candidate.id,
        )
        pool = repairable or self.selector.frontier(candidates)
        return [self.random.choice(pool) for _ in strategies] if pool else []

    def _feedback(
        self,
        generation: int,
        parent: Candidate,
        reports: dict[str, CheckReport],
        baseline_report: CheckReport,
        candidates: list[Candidate],
    ) -> OptimizationFeedback | None:
        if generation <= 1 or parent.id not in reports:
            return None
        return FeedbackBuilder().build(parent, baseline_report, reports[parent.id], self.selector.frontier(candidates))

    def _source_snapshot(self, parent: Candidate, baseline: DocumentationSnapshot) -> DocumentationSnapshot:
        root = Path(parent.artifact_dir) / "candidate" if parent.artifact_dir else None
        if root and root.exists():
            return discover_markdown(root, self.config, ApproximateTokenCounter())
        return baseline

    def _update_statuses(self, candidates: list[Candidate], frontier_ids: set[str]) -> None:
        for item in candidates:
            if item.status != CandidateStatus.REJECTED:
                item.status = CandidateStatus.FRONTIER if item.id in frontier_ids else CandidateStatus.DOMINATED

    def _max_generations(self) -> int:
        return 1 if self.runtime.mode != OptimizeMode.SEARCH else self.runtime.search.generations

    def _candidate_summary(self, candidate: Candidate) -> str:
        operations = ",".join(operation.type for operation in candidate.proposal.operations) or "baseline"
        return f"{candidate.id}:{candidate.status.value}:{operations}"

    def _last_usage(self, component: object | None) -> ProviderUsage:
        usage = getattr(component, "last_usage", None)
        return usage if isinstance(usage, ProviderUsage) else ProviderUsage(requests=0)

    def _effective_context(self, evaluation: EvaluationResult | None) -> dict[str, list[str]]:
        raw = evaluation.raw_summary.get("effective_context", {}) if evaluation else {}
        return cast(dict[str, list[str]], raw) if isinstance(raw, dict) else {}

    def _evaluation_cost(self, usage: ProviderUsage) -> CandidateCost:
        return CandidateCost(
            evaluation_requests=usage.requests,
            evaluation_input_tokens=usage.input_tokens,
            evaluation_output_tokens=usage.output_tokens,
            total_cost=usage.cost_usd,
            cache_hits=usage.cache_hits,
            cost_sources=[usage.cost_source] if usage.requests else [],
        )

    def _external_capability_enabled(self) -> bool:
        return any(
            (
                self.generator.semantic is not None,
                self.evaluator is not None,
                self.semantic_invariant_discoverer is not None,
                self.semantic_invariant_verifier is not None,
                self.prompt_suboptimizer is not None,
            )
        )

    def _budget_exhausted(self, candidates: list[Candidate]) -> bool:
        if not self._external_capability_enabled():
            return False
        total = self._total_cost(candidates)
        budget = self.runtime.search
        return (
            total.external_requests >= budget.max_llm_requests
            or (budget.max_cost_usd is not None and total.total_cost >= budget.max_cost_usd)
            or (budget.max_input_tokens is not None and total.input_tokens >= budget.max_input_tokens)
            or (budget.max_output_tokens is not None and total.output_tokens >= budget.max_output_tokens)
        )

    def _would_exceed_after(self, candidates_cost: CandidateCost | None, extra: ProviderUsage) -> bool:
        if candidates_cost is None:
            return False
        return candidates_cost.external_requests + extra.requests >= self.runtime.search.max_llm_requests

    def _budget_stop_reason(self, candidates: list[Candidate]) -> StopReason:
        total = self._total_cost(candidates)
        budget = self.runtime.search
        if total.external_requests >= budget.max_llm_requests:
            return StopReason.REQUEST_BUDGET
        if budget.max_cost_usd is not None and total.total_cost >= budget.max_cost_usd:
            return StopReason.COST_BUDGET
        return StopReason.TOKEN_BUDGET

    def _total_cost(self, candidates: list[Candidate]) -> CandidateCost:
        costs = [candidate.creation_cost for candidate in candidates]
        return CandidateCost(
            deterministic_operations=sum(cost.deterministic_operations for cost in costs),
            generation_requests=sum(cost.generation_requests for cost in costs),
            evaluation_requests=sum(cost.evaluation_requests for cost in costs),
            prompt_suboptimizer_requests=sum(cost.prompt_suboptimizer_requests for cost in costs),
            generation_input_tokens=sum(cost.generation_input_tokens for cost in costs),
            generation_output_tokens=sum(cost.generation_output_tokens for cost in costs),
            evaluation_input_tokens=sum(cost.evaluation_input_tokens for cost in costs),
            evaluation_output_tokens=sum(cost.evaluation_output_tokens for cost in costs),
            prompt_suboptimizer_input_tokens=sum(cost.prompt_suboptimizer_input_tokens for cost in costs),
            prompt_suboptimizer_output_tokens=sum(cost.prompt_suboptimizer_output_tokens for cost in costs),
            cache_hits=sum(cost.cache_hits for cost in costs),
            total_cost=sum((cost.total_cost for cost in costs), Decimal("0")),
            cost_sources=sorted({source for cost in costs for source in cost.cost_sources}),
        )

    def _gepa_reason(self, performed: bool) -> str:
        if performed:
            return "optimized eligible marked prompt"
        return "no eligible prompt artifact/provider" if self.runtime.gepa.enabled else "disabled"


def _combine_usage(*items: ProviderUsage) -> ProviderUsage:
    active = [item for item in items if item.requests]
    return ProviderUsage(
        requests=sum(item.requests for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        cost_usd=sum((item.cost_usd for item in items), Decimal("0")),
        cost_source="mixed" if len({item.cost_source for item in active}) > 1 else (active[0].cost_source if active else "provider"),
        cache_hits=sum(item.cache_hits for item in items),
    )
