from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
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
    CandidateFingerprint,
    CandidateStatus,
    InvariantDecision,
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
from ai_doc.providers.semantic import ProviderUsage, SemanticBudgetExceeded, UsageDrainer
from ai_doc.reporting.models import CheckReport
from ai_doc.tokens.counter import ApproximateTokenCounter

BASELINE_CANDIDATE_ID = "baseline"
GEPA_MARKER = "<!-- ai-doc:gepa -->"
BUDGET_REJECTION = "external budget exhausted before required candidate evaluation"


@dataclass
class SearchResult:
    run: OptimizationRun
    run_dir: Path
    baseline_report: CheckReport
    reports: dict[str, CheckReport]


@dataclass
class SearchState:
    candidates: list[Candidate]
    reports: dict[str, CheckReport]
    fingerprints: set[str] = field(default_factory=set)
    memory: SearchMemory = field(default_factory=SearchMemory)
    generated_count: int = 0
    stagnant: int = 0
    gepa_performed: bool = False
    budget_stop_stage: str | None = None


@dataclass(frozen=True)
class EvaluationContext:
    baseline: DocumentationSnapshot
    suite: EvaluationSuite
    baseline_report: CheckReport
    invariants: list[Invariant]
    critical_count: int
    run_dir: Path


@dataclass(frozen=True)
class CandidateDraft:
    candidate_id: str
    generation: int
    parent: Candidate
    strategy: str
    proposal: CandidateProposal
    rendered: dict[str, str]
    source: DocumentationSnapshot
    feedback: OptimizationFeedback | None
    generation_usage: ProviderUsage
    gepa_usage: ProviderUsage


@dataclass(frozen=True)
class CandidateWorkspace:
    candidate_dir: Path
    diff_path: Path
    report: CheckReport
    snapshot: DocumentationSnapshot


@dataclass(frozen=True)
class CandidateProcessResult:
    entered_frontier: bool = False
    stop_reason: StopReason | None = None


@dataclass(frozen=True)
class GepaStageResult:
    draft: CandidateDraft
    workspace: CandidateWorkspace
    rejected: bool = False
    stop_reason: StopReason | None = None


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
        baseline_candidate = self._baseline_candidate(baseline_report, critical_count, None, discovery_usage)
        state = SearchState(
            candidates=[baseline_candidate],
            reports={BASELINE_CANDIDATE_ID: baseline_report},
        )
        context = EvaluationContext(baseline, suite, baseline_report, invariants, critical_count, run_dir)
        initial_stop = self._budget_stop_for_candidates(state.candidates)
        if initial_stop is not None:
            state.budget_stop_stage = "semantic invariant discovery"
            run = self._build_run(state, baseline_candidate, initial_stop, run_dir)
            return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=state.reports)

        baseline_evaluation, baseline_eval_usage = self._semantic_evaluate(baseline, None, suite)
        baseline_candidate.evaluation = baseline_evaluation
        baseline_candidate.objective_vector = objective_from_report(
            baseline_report,
            [],
            critical_count,
            baseline_evaluation,
        )
        baseline_candidate.creation_cost = self._evaluation_cost(_combine_usage(discovery_usage, baseline_eval_usage))
        baseline_candidate.evidence.effective_context = self._effective_context(baseline_evaluation)
        baseline_stop = self._budget_stop_for_candidates(state.candidates)
        if baseline_stop is not None:
            state.budget_stop_stage = "baseline semantic evaluation"
            run = self._build_run(state, baseline_candidate, baseline_stop, run_dir)
            return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=state.reports)

        stop_reason = self._search_generations(state, context, baseline_candidate)
        run = self._build_run(state, baseline_candidate, stop_reason, run_dir)
        return SearchResult(run=run, run_dir=run_dir, baseline_report=baseline_report, reports=state.reports)

    def _search_generations(
        self, state: SearchState, context: EvaluationContext, baseline_candidate: Candidate
    ) -> StopReason:
        generation = 1
        while generation <= self._max_generations():
            strategies = self._strategies(generation)
            parents = self._parents(generation, strategies, state.candidates, baseline_candidate)
            entered = False
            for index, strategy in enumerate(strategies):
                stop_reason = self._pre_candidate_stop(state)
                if stop_reason is not None:
                    return stop_reason
                parent = parents[index] if index < len(parents) else baseline_candidate
                outcome = self._process_candidate(state, context, generation, strategy, parent)
                entered = entered or outcome.entered_frontier
                if outcome.stop_reason is not None:
                    return outcome.stop_reason
            state.stagnant = 0 if entered else state.stagnant + 1
            if self.runtime.search.patience and state.stagnant >= self.runtime.search.patience:
                return StopReason.PATIENCE
            generation += 1
        return StopReason.GENERATION_COMPLETE

    def _process_candidate(
        self,
        state: SearchState,
        context: EvaluationContext,
        generation: int,
        strategy: GenerationStrategyName,
        parent: Candidate,
    ) -> CandidateProcessResult:
        feedback = self._feedback(generation, parent, state.reports, context.baseline_report, state.candidates)
        source = self._source_snapshot(parent, context.baseline)
        try:
            proposal, rendered = self.generator.generate(
                source,
                context.invariants,
                strategy,
                previous_summaries=[self._candidate_summary(item) for item in state.candidates],
                explored_transformations=sorted(state.fingerprints),
                feedback=feedback,
                memory=state.memory,
            )
        except SemanticBudgetExceeded:
            state.budget_stop_stage = "semantic candidate generation"
            stop = self._budget_stop_for_candidates(state.candidates) or StopReason.REQUEST_BUDGET
            return CandidateProcessResult(stop_reason=stop)

        draft = CandidateDraft(
            candidate_id=f"C{state.generated_count + 1:03d}",
            generation=generation,
            parent=parent,
            strategy=str(strategy),
            proposal=proposal,
            rendered=rendered,
            source=source,
            feedback=feedback,
            generation_usage=self._last_usage(self.generator.semantic),
            gepa_usage=ProviderUsage(requests=0),
        )
        workspace = self._materialize_candidate(draft, context)
        cheap_failures = hard_constraint_failures(workspace.report, [], None, context.baseline_report)
        if cheap_failures:
            candidate = self._static_rejected_candidate(draft, context, workspace, cheap_failures)
            self._record_candidate(state, candidate, workspace.report, feedback)
            return CandidateProcessResult()

        generation_stop = self._budget_stop_with_extra(state.candidates, self._draft_cost(draft))
        if generation_stop is not None:
            candidate = self._static_rejected_candidate(draft, context, workspace, [BUDGET_REJECTION])
            self._record_candidate(state, candidate, workspace.report, feedback)
            state.budget_stop_stage = "semantic candidate generation"
            return CandidateProcessResult(stop_reason=generation_stop)

        gepa_stage = self._prepare_gepa_stage(state, context, draft, workspace)
        if gepa_stage.rejected or gepa_stage.stop_reason is not None:
            return CandidateProcessResult(stop_reason=gepa_stage.stop_reason)

        candidate, report, candidate_stop = self._evaluate_candidate(
            gepa_stage.draft,
            context,
            state.fingerprints,
            gepa_stage.workspace,
            state.candidates,
        )
        self._record_candidate(state, candidate, report, feedback)
        frontier_ids = {item.id for item in self.selector.frontier(state.candidates)}
        entered = candidate.id in frontier_ids and candidate.status != CandidateStatus.REJECTED
        self._update_statuses(state.candidates, frontier_ids)
        if candidate_stop is not None:
            state.budget_stop_stage = "candidate safety/evaluation"
        return CandidateProcessResult(entered_frontier=entered, stop_reason=candidate_stop)

    def _prepare_gepa_stage(
        self,
        state: SearchState,
        context: EvaluationContext,
        draft: CandidateDraft,
        workspace: CandidateWorkspace,
    ) -> GepaStageResult:
        if not self.runtime.gepa.enabled:
            return GepaStageResult(draft, workspace)
        try:
            proposal, rendered, gepa_usage, performed = self._apply_gepa(
                draft.source,
                draft.proposal,
                draft.rendered,
                context.suite,
            )
        except SemanticBudgetExceeded:
            candidate = self._static_rejected_candidate(draft, context, workspace, [BUDGET_REJECTION])
            self._record_candidate(state, candidate, workspace.report, draft.feedback)
            state.budget_stop_stage = "prompt suboptimization"
            stop = self._budget_stop_for_candidates(state.candidates) or StopReason.REQUEST_BUDGET
            return GepaStageResult(draft, workspace, rejected=True, stop_reason=stop)

        state.gepa_performed = state.gepa_performed or performed
        updated_draft = replace(draft, proposal=proposal, rendered=rendered, gepa_usage=gepa_usage)
        updated_workspace = self._materialize_candidate(updated_draft, context)
        post_gepa_failures = hard_constraint_failures(
            updated_workspace.report,
            [],
            None,
            context.baseline_report,
        )
        if post_gepa_failures:
            candidate = self._static_rejected_candidate(
                updated_draft,
                context,
                updated_workspace,
                post_gepa_failures,
            )
            self._record_candidate(state, candidate, updated_workspace.report, draft.feedback)
            return GepaStageResult(updated_draft, updated_workspace, rejected=True)

        gepa_stop = self._budget_stop_with_extra(state.candidates, self._draft_cost(updated_draft))
        if gepa_stop is not None:
            candidate = self._static_rejected_candidate(
                updated_draft,
                context,
                updated_workspace,
                [BUDGET_REJECTION],
            )
            self._record_candidate(state, candidate, updated_workspace.report, draft.feedback)
            state.budget_stop_stage = "prompt suboptimization"
            return GepaStageResult(updated_draft, updated_workspace, rejected=True, stop_reason=gepa_stop)
        return GepaStageResult(updated_draft, updated_workspace)

    def _materialize_candidate(self, draft: CandidateDraft, context: EvaluationContext) -> CandidateWorkspace:
        candidate_dir = context.run_dir / "candidates" / draft.candidate_id
        candidate_dir.mkdir(parents=True, exist_ok=True)
        write_proposal(draft.proposal, candidate_dir)
        tree = write_candidate_tree(draft.source, draft.rendered, candidate_dir)
        copy_untracked_context(context.baseline.root, tree)
        diff_path = write_diff(draft.source, draft.rendered, candidate_dir)
        report = run_static_check(tree, self.config, extensions=self.extensions)
        snapshot = discover_markdown(tree, self.config, ApproximateTokenCounter())
        return CandidateWorkspace(candidate_dir, diff_path, report, snapshot)

    def _static_rejected_candidate(
        self,
        draft: CandidateDraft,
        context: EvaluationContext,
        workspace: CandidateWorkspace,
        failures: list[str],
    ) -> Candidate:
        regressions, decisions = verify_invariants_with_evidence(context.invariants, workspace.snapshot, None)
        all_failures = list(
            dict.fromkeys(
                [
                    *failures,
                    *hard_constraint_failures(
                        workspace.report,
                        regressions,
                        None,
                        context.baseline_report,
                    ),
                ]
            )
        )
        candidate = self._make_candidate(
            draft,
            context,
            workspace,
            regressions,
            decisions,
            None,
            ProviderUsage(requests=0),
            all_failures,
        )
        self._write_candidate_evidence(candidate, workspace, evaluation=None)
        return candidate

    def _evaluate_candidate(
        self,
        draft: CandidateDraft,
        context: EvaluationContext,
        fingerprints: set[str],
        workspace: CandidateWorkspace,
        prior_candidates: list[Candidate],
    ) -> tuple[Candidate, CheckReport, StopReason | None]:
        regressions, decisions = verify_invariants_with_evidence(
            context.invariants,
            workspace.snapshot,
            self.semantic_invariant_verifier,
        )
        invariant_usage = self._drain_invariant_usage()
        fingerprint = fingerprint_candidate(
            draft.rendered,
            [operation.type for operation in draft.proposal.operations],
        )
        duplicate = fingerprint.content_hash in fingerprints
        fingerprints.add(fingerprint.content_hash)
        tier0 = hard_constraint_failures(workspace.report, regressions, None, context.baseline_report)
        partial_cost = self._candidate_cost(
            draft.proposal,
            draft.generation_usage,
            invariant_usage,
            draft.gepa_usage,
        )
        budget_stop = self._budget_stop_with_extra(prior_candidates, partial_cost)
        if tier0 or duplicate or budget_stop is not None:
            evaluation = None
            semantic_usage = ProviderUsage(requests=0)
        else:
            evaluation, semantic_usage = self._semantic_evaluate(context.baseline, workspace.snapshot, context.suite)
        evaluation_usage = _combine_usage(invariant_usage, semantic_usage)
        failures = hard_constraint_failures(workspace.report, regressions, evaluation, context.baseline_report)
        if duplicate:
            failures.append("duplicate candidate fingerprint")
        if budget_stop is not None:
            failures.append(BUDGET_REJECTION)
        candidate = self._make_candidate(
            draft,
            context,
            workspace,
            regressions,
            decisions,
            evaluation,
            evaluation_usage,
            failures,
            fingerprint=fingerprint,
        )
        self._write_candidate_evidence(candidate, workspace, evaluation)
        full_stop = self._budget_stop_with_extra(prior_candidates, candidate.creation_cost)
        return candidate, workspace.report, full_stop

    def _make_candidate(
        self,
        draft: CandidateDraft,
        context: EvaluationContext,
        workspace: CandidateWorkspace,
        regressions: list[str],
        decisions: list[InvariantDecision],
        evaluation: EvaluationResult | None,
        evaluation_usage: ProviderUsage,
        failures: list[str],
        fingerprint: CandidateFingerprint | None = None,
    ) -> Candidate:
        cost = self._candidate_cost(
            draft.proposal,
            draft.generation_usage,
            evaluation_usage,
            draft.gepa_usage,
        )
        evidence = CandidateEvidence(
            generation_reason="; ".join(operation.reason for operation in draft.proposal.operations),
            feedback=draft.feedback,
            invariant_decisions=decisions,
            effective_context=self._effective_context(evaluation),
        )
        return Candidate(
            id=draft.candidate_id,
            parent_ids=[draft.parent.id],
            strategy=draft.strategy,
            proposal=draft.proposal,
            objective_vector=objective_from_report(
                workspace.report,
                regressions,
                context.critical_count,
                evaluation,
            ),
            evaluation=evaluation,
            status=CandidateStatus.REJECTED if failures else CandidateStatus.VALID,
            generation=draft.generation,
            creation_cost=cost,
            fingerprint=fingerprint,
            rejection_reasons=list(dict.fromkeys(failures)),
            artifact_dir=str(workspace.candidate_dir),
            evidence=evidence,
        )

    def _write_candidate_evidence(
        self,
        candidate: Candidate,
        workspace: CandidateWorkspace,
        evaluation: EvaluationResult | None,
    ) -> None:
        eval_evidence = evaluation or EvaluationResult(
            engine="tier0-static",
            passed=candidate.status != CandidateStatus.REJECTED,
            raw_summary={"diff": str(workspace.diff_path), "semantic": False},
        )
        (workspace.candidate_dir / "evaluation.json").write_text(
            eval_evidence.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (workspace.candidate_dir / "evidence.json").write_text(
            candidate.evidence.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _record_candidate(
        self,
        state: SearchState,
        candidate: Candidate,
        report: CheckReport,
        feedback: OptimizationFeedback | None,
    ) -> None:
        state.candidates.append(candidate)
        state.reports[candidate.id] = report
        state.generated_count += 1
        if feedback:
            frontier_ids = {item.id for item in self.selector.frontier(state.candidates)}
            state.memory = update_search_memory(state.memory, feedback, candidate.id in frontier_ids)

    def _build_run(
        self,
        state: SearchState,
        baseline_candidate: Candidate,
        stop_reason: StopReason,
        run_dir: Path,
    ) -> OptimizationRun:
        frontier = self.selector.frontier(state.candidates)
        recommended = self.recommendation.choose(baseline_candidate, frontier)
        reason = (
            f"recommended {recommended.id}: non-dominated and policy-qualified"
            if recommended
            else "baseline/no-change retained: no candidate satisfied recommendation policy"
        )
        return OptimizationRun(
            run_id=run_dir.name,
            strategy=self.runtime.mode.value,
            seed=self.runtime.seed,
            candidates=state.candidates,
            frontier=self.archive_builder.build(state.candidates),
            recommended_candidate_id=recommended.id if recommended else None,
            recommendation_reason=reason,
            search_memory=state.memory,
            stopped_reason=stop_reason,
            total_cost=self._total_cost(state.candidates),
            metadata={
                "baseline_in_frontier": any(item.id == BASELINE_CANDIDATE_ID for item in frontier),
                "semantic_evaluation": self.evaluator is not None,
                "budget_stop_stage": state.budget_stop_stage,
                "gepa": {
                    **self.runtime.gepa.model_dump(),
                    "performed": state.gepa_performed,
                    "reason": self._gepa_reason(state.gepa_performed),
                },
            },
        )

    def _baseline_candidate(
        self,
        report: CheckReport,
        critical_count: int,
        evaluation: EvaluationResult | None,
        usage: ProviderUsage,
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
            PromptArtifact(id=eligible.relative_path, text=current),
            suite,
            self.runtime.search,
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
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> tuple[EvaluationResult | None, ProviderUsage]:
        if self.evaluator is None or not suite.scenarios:
            return None, ProviderUsage(requests=0)
        result = self.evaluator.evaluate(baseline, candidate, suite)
        component = getattr(self.evaluator, "evaluator", self.evaluator)
        if isinstance(component, UsageDrainer):
            usage = component.drain_usage()
        else:
            usage = self._last_usage(component)
            if not usage.requests:
                usage = ProviderUsage(requests=len(suite.scenarios))
        return result, usage

    def _drain_invariant_usage(self) -> ProviderUsage:
        verifier = self.semantic_invariant_verifier or self.semantic_invariant_discoverer
        return verifier.drain_usage() if isinstance(verifier, UsageDrainer) else ProviderUsage(requests=0)

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

    def _draft_cost(self, draft: CandidateDraft) -> CandidateCost:
        return self._candidate_cost(
            draft.proposal,
            draft.generation_usage,
            ProviderUsage(requests=0),
            draft.gepa_usage,
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
        self,
        generation: int,
        strategies: list[GenerationStrategyName],
        candidates: list[Candidate],
        baseline: Candidate,
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

    def _pre_candidate_stop(self, state: SearchState) -> StopReason | None:
        if state.generated_count >= self.runtime.search.max_candidates:
            return StopReason.CANDIDATE_BUDGET
        return self._budget_stop_for_candidates(state.candidates)

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

    def _budget_stop_for_candidates(self, candidates: list[Candidate]) -> StopReason | None:
        if not self._external_capability_enabled():
            return None
        return self._budget_stop_for_cost(self._total_cost(candidates))

    def _budget_stop_with_extra(
        self,
        candidates: list[Candidate],
        extra: CandidateCost,
    ) -> StopReason | None:
        if not self._external_capability_enabled():
            return None
        return self._budget_stop_for_cost(self._sum_costs([self._total_cost(candidates), extra]))

    def _budget_stop_for_cost(self, total: CandidateCost) -> StopReason | None:
        budget = self.runtime.search
        if total.external_requests >= budget.max_llm_requests:
            return StopReason.REQUEST_BUDGET
        if budget.max_cost_usd is not None and total.total_cost >= budget.max_cost_usd:
            return StopReason.COST_BUDGET
        if budget.max_input_tokens is not None and total.input_tokens >= budget.max_input_tokens:
            return StopReason.TOKEN_BUDGET
        if budget.max_output_tokens is not None and total.output_tokens >= budget.max_output_tokens:
            return StopReason.TOKEN_BUDGET
        return None

    def _total_cost(self, candidates: list[Candidate]) -> CandidateCost:
        return self._sum_costs([candidate.creation_cost for candidate in candidates])

    def _sum_costs(self, costs: list[CandidateCost]) -> CandidateCost:
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
    sources = {item.cost_source for item in active}
    cost_source = "mixed" if len(sources) > 1 else (active[0].cost_source if active else "provider")
    return ProviderUsage(
        requests=sum(item.requests for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        cost_usd=sum((item.cost_usd for item in items), Decimal("0")),
        cost_source=cost_source,
        cache_hits=sum(item.cache_hits for item in items),
    )
