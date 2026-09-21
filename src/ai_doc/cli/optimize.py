from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer

from ai_doc.app import load_suite
from ai_doc.cli.config_warnings import warn_if_explicit_config_disables_observability
from ai_doc.composition import (
    register_configured_extensions,
    resolve_configured_evaluator,
    resolve_recommendation_policy,
    resolve_semantic_provider,
    resolve_token_counter,
)
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.config.models import AiDocConfig
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import Evaluator, PairwiseSemanticEvaluator
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.evaluators.deepeval import DeepEvalEvaluator, DeepEvalUnavailableError
from ai_doc.extensions.process import ProcessExtensionError
from ai_doc.observability import (
    ObservationRecord,
    ObservationTimer,
    ObservationWriteError,
    append_observation,
    optimize_observation,
)
from ai_doc.optimizer.generator import SemanticCandidateGenerator
from ai_doc.optimizer.invariants import SemanticInvariantDiscoverer, SemanticInvariantVerifier
from ai_doc.optimizer.prompt_suboptimizer import PromptSubOptimizer
from ai_doc.optimizer.search import SearchController, SearchResult
from ai_doc.optimizer.semantic import (
    ProviderPairwiseSemanticEvaluator,
    ProviderPromptSubOptimizer,
    ProviderSemanticCandidateGenerator,
    ProviderSemanticEvaluator,
    ProviderSemanticInvariantService,
)
from ai_doc.optimizer.source_discovery import discover_optimization_sources, run_optimization_static_check
from ai_doc.plugins.loader import ExtensionError, load_extensions
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.providers.semantic import SEMANTIC_COMMAND_ENV, SemanticProvider
from ai_doc.reporting.console import render_search_optimize_console
from ai_doc.reporting.json import render_json
from ai_doc.reporting.models import CheckReport, SearchOptimizeReport
from ai_doc.root import discover_project_root
from ai_doc.tokens.counter import TokenCounter


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


@dataclass
class SemanticStack:
    provider: SemanticProvider | None = None
    generator: SemanticCandidateGenerator | None = None
    invariant_verifier: SemanticInvariantVerifier | None = None
    invariant_discoverer: SemanticInvariantDiscoverer | None = None
    evaluator: Evaluator | None = None
    pairwise_evaluator: PairwiseSemanticEvaluator | None = None
    prompt_suboptimizer: PromptSubOptimizer | None = None


@dataclass
class OptimizeInputs:
    config: AiDocConfig
    extensions: ExtensionRegistry
    token_counter: TokenCounter
    baseline_report: CheckReport
    baseline_snapshot: DocumentationSnapshot
    static_duration_ms: int


@dataclass(frozen=True)
class OptimizeCompletion:
    report: SearchOptimizeReport
    exit_code: int
    rendered_report: str


def optimize_command(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    path: Annotated[Path, typer.Argument(help="Repository root to optimize.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
    output_format: Annotated[OutputFormat, typer.Option("--format", help="Output format.")] = OutputFormat.CONSOLE,
    output: Annotated[Path, typer.Option("--output", help="Output directory.")] = Path(".ai-doc-output"),
    candidates: Annotated[int | None, typer.Option("--candidates", help="Initial candidates.")] = None,
    generations: Annotated[int | None, typer.Option("--generations", help="Search generations.")] = None,
    max_candidates: Annotated[int | None, typer.Option("--max-candidates", help="Maximum generated candidates.")] = None,
    max_cost: Annotated[float | None, typer.Option("--max-cost", help="Maximum optimizer cost USD.")] = None,
    max_requests: Annotated[int | None, typer.Option("--max-requests", help="Maximum external model requests.")] = None,
    strategy: Annotated[OptimizeMode | None, typer.Option("--strategy", help="Optimization mode.")] = None,
    deep: Annotated[bool, typer.Option("--deep", help="Run semantic evaluation on task-selected context.")] = False,
    pairwise_semantic: Annotated[
        bool,
        typer.Option(
            "--pairwise-semantic",
            help="Run B-tier pairwise semantic judging for candidates that survive earlier gates.",
        ),
    ] = False,
    require_pairwise_semantic: Annotated[
        bool,
        typer.Option(
            "--require-pairwise-semantic",
            help="Require at least one pairwise semantic comparison to actually run.",
        ),
    ] = False,
    gepa: Annotated[bool, typer.Option("--gepa", help="Enable GEPA prompt sub-optimizer.")] = False,
    seed: Annotated[int | None, typer.Option("--seed", help="Random seed.")] = None,
    show_frontier: Annotated[bool, typer.Option("--show-frontier", help="Print all frontier candidates.")] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Do not prompt before external calls.")
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Keep adapter temporary files.")] = False,
    experimental_gepa: Annotated[bool, typer.Option("--experimental-gepa", help="Alias for --gepa.")] = False,
) -> None:
    timer = ObservationTimer()
    project_root = discover_project_root(path, root)
    output_root = (project_root / output).resolve() if not output.is_absolute() else output
    try:
        inputs = _load_optimize_inputs(project_root, config, debug, output_root)
    except (ConfigError, ExtensionError, ProcessExtensionError, KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    runtime = RuntimeSearchConfig(
        mode=strategy or inputs.config.optimization.strategy,
        population=inputs.config.optimization.population.model_copy(deep=True),
        search=inputs.config.optimization.search.model_copy(deep=True),
        pareto=inputs.config.optimization.pareto.model_copy(deep=True),
        gepa=inputs.config.optimization.gepa.model_copy(
            update={"enabled": gepa or experimental_gepa or inputs.config.optimization.gepa.enabled}
        ),
        recommendation=inputs.config.optimization.recommendation.model_copy(deep=True),
        exploration_rate=inputs.config.optimization.exploration_rate,
        restart_after_stagnation=inputs.config.optimization.restart_after_stagnation,
        concurrency=inputs.config.optimization.concurrency,
        seed=seed or inputs.config.optimization.gepa.random_seed,
        pairwise_semantic=pairwise_semantic
        or require_pairwise_semantic
        or inputs.config.optimization.pairwise_semantic,
    )
    _apply_overrides(runtime, candidates, generations, max_candidates, max_cost, max_requests)
    if runtime.mode == OptimizeMode.CONSERVATIVE:
        runtime.population.initial_candidates = 1
        runtime.search.max_candidates = 1
        runtime.search.generations = 1

    suite = load_suite(project_root)
    semantic = _build_semantic_stack(inputs.config, inputs.extensions, runtime, deep)
    configured_evaluator = resolve_configured_evaluator(inputs.config, inputs.extensions, "deep") if deep else None
    if configured_evaluator is not None:
        semantic.evaluator = ScenarioContextEvaluator(configured_evaluator)
    if semantic.provider:
        typer.echo(
            f"Semantic provider enabled; {SEMANTIC_COMMAND_ENV} or configured provider may be used.",
            err=True,
        )
    if deep:
        interaction = "non-interactive" if non_interactive else "interactive"
        typer.echo(f"Semantic evaluation enabled ({interaction}); external calls may occur.", err=True)

    try:
        controller = SearchController(
            inputs.config,
            runtime,
            output_root,
            extensions=inputs.extensions,
            token_counter=inputs.token_counter,
            recommendation_policy=resolve_recommendation_policy(
                inputs.config,
                inputs.extensions,
                default_policy=SearchController.default_recommendation_policy(runtime),
            ),
            evaluator=semantic.evaluator,
            pairwise_semantic_evaluator=semantic.pairwise_evaluator,
            semantic_generator=semantic.generator,
            semantic_invariant_verifier=semantic.invariant_verifier,
            semantic_invariant_discoverer=semantic.invariant_discoverer,
            prompt_suboptimizer=semantic.prompt_suboptimizer,
        )
        optimize_started = perf_counter()
        result = controller.optimize(inputs.baseline_snapshot, suite, inputs.baseline_report)
        optimize_duration_ms = _elapsed_ms(optimize_started)
    except (DeepEvalUnavailableError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    completion = _complete_optimize_result(
        inputs=inputs,
        result=result,
        require_pairwise_semantic=require_pairwise_semantic,
        output_format=output_format,
        show_frontier=show_frontier,
    )
    _safe_append_observation(
        project_root,
        inputs.config,
        optimize_observation(
            timer=timer,
            root=project_root,
            config=inputs.config,
            report=completion.report,
            status="completed",
            exit_code=completion.exit_code,
            static_duration_ms=inputs.static_duration_ms,
            optimize_duration_ms=optimize_duration_ms,
        ),
    )
    typer.echo(completion.rendered_report)
    raise typer.Exit(completion.exit_code)


def _complete_optimize_result(
    *,
    inputs: OptimizeInputs,
    result: SearchResult,
    require_pairwise_semantic: bool,
    output_format: OutputFormat,
    show_frontier: bool,
) -> OptimizeCompletion:
    search_result = result
    generated_candidates = [candidate for candidate in search_result.run.candidates if candidate.id != "baseline"]
    rejected_candidates = [candidate for candidate in search_result.run.candidates if candidate.status == "rejected"]
    recommended = next(
        (
            candidate
            for candidate in search_result.run.candidates
            if candidate.id == search_result.run.recommended_candidate_id
        ),
        None,
    )
    report = SearchOptimizeReport(
        baseline=inputs.baseline_report,
        run=search_result.run,
        candidates_evaluated=len(generated_candidates),
        candidates_rejected=len(rejected_candidates),
        frontier=search_result.run.frontier.entries,
        recommended_candidate=recommended,
        baseline_in_frontier=bool(search_result.run.metadata.get("baseline_in_frontier")),
    )
    _write_run_artifacts(search_result.run_dir, report)
    pairwise_postcondition_failed = require_pairwise_semantic and search_result.run.pairwise_comparisons_performed == 0
    if search_result.run.pairwise_semantic_requested and search_result.run.pairwise_comparisons_performed == 0:
        _warn_pairwise_not_performed(required=require_pairwise_semantic)
    exit_code = 3 if pairwise_postcondition_failed else 4 if not search_result.run.recommended_candidate_id else 0
    rendered_report = (
        render_json(report)
        if output_format == OutputFormat.JSON
        else render_search_optimize_console(report, show_frontier=show_frontier)
    )
    return OptimizeCompletion(report=report, exit_code=exit_code, rendered_report=rendered_report)


def _warn_pairwise_not_performed(*, required: bool) -> None:
    heading = (
        "Required pairwise semantic judging was not performed:"
        if required
        else "Pairwise semantic judging was requested but not performed:"
    )
    typer.echo(heading, err=True)
    typer.echo("0 candidates reached the B-tier after earlier gates.", err=True)
    typer.echo("This run did NOT receive a pairwise semantic judgment.", err=True)


def _load_optimize_inputs(project_root: Path, config: Path | None, debug: bool, output_root: Path) -> OptimizeInputs:
    loaded = load_config(project_root, config)
    warn_if_explicit_config_disables_observability(config, loaded)
    extensions = load_extensions(project_root, loaded.extensions, debug=debug)
    register_configured_extensions(loaded, extensions)
    token_counter = resolve_token_counter(loaded, extensions)
    static_started = perf_counter()
    baseline_report = run_optimization_static_check(project_root, loaded, extensions, token_counter, output_root)
    return OptimizeInputs(
        config=loaded,
        extensions=extensions,
        token_counter=token_counter,
        baseline_report=baseline_report,
        baseline_snapshot=discover_optimization_sources(project_root, loaded, token_counter, output_root),
        static_duration_ms=_elapsed_ms(static_started),
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _safe_append_observation(project_root: Path, config: AiDocConfig, record: ObservationRecord) -> None:
    try:
        append_observation(project_root, config, record)
    except ObservationWriteError as exc:
        typer.echo(f"Observation logging failed: {exc}", err=True)


def _build_semantic_stack(
    config: AiDocConfig,
    extensions: ExtensionRegistry,
    runtime: RuntimeSearchConfig,
    deep: bool,
) -> SemanticStack:
    if runtime.mode == OptimizeMode.CONSERVATIVE:
        provider = None
    else:
        provider = resolve_semantic_provider(
            config,
            extensions,
            max_requests=runtime.search.max_llm_requests,
            max_input_tokens=runtime.search.max_input_tokens,
            max_output_tokens=runtime.search.max_output_tokens,
            max_cost_usd=runtime.search.max_cost_usd,
        )
    if provider is None:
        deep_config = config.evaluation.get("deep")
        evaluator_model = deep_config.model if deep_config is not None else None
        evaluator = ScenarioContextEvaluator(DeepEvalEvaluator(model=evaluator_model)) if deep else None
        deepeval_pairwise: PairwiseSemanticEvaluator | None = (
            DeepEvalEvaluator(model=config.optimization.deepeval_model)
            if runtime.pairwise_semantic and runtime.mode != OptimizeMode.CONSERVATIVE
            else None
        )
        return SemanticStack(evaluator=evaluator, pairwise_evaluator=deepeval_pairwise)
    invariant_service = ProviderSemanticInvariantService(provider)
    evaluator = ScenarioContextEvaluator(ProviderSemanticEvaluator(provider)) if deep else None
    provider_pairwise: PairwiseSemanticEvaluator | None = (
        ProviderPairwiseSemanticEvaluator(provider) if runtime.pairwise_semantic else None
    )
    return SemanticStack(
        provider=provider,
        generator=ProviderSemanticCandidateGenerator(provider),
        invariant_verifier=invariant_service,
        invariant_discoverer=invariant_service,
        evaluator=evaluator,
        pairwise_evaluator=provider_pairwise,
        prompt_suboptimizer=ProviderPromptSubOptimizer(provider) if runtime.gepa.enabled else None,
    )


def _apply_overrides(
    runtime: RuntimeSearchConfig,
    candidates: int | None,
    generations: int | None,
    max_candidates: int | None,
    max_cost: float | None,
    max_requests: int | None,
) -> None:
    if candidates is not None:
        runtime.population.initial_candidates = candidates
        runtime.search.initial_candidates = candidates
    if generations is not None:
        runtime.search.generations = generations
    if max_candidates is not None:
        runtime.search.max_candidates = max_candidates
    if max_cost is not None:
        runtime.search.max_cost_usd = Decimal(str(max_cost))
    if max_requests is not None:
        runtime.search.max_llm_requests = max_requests


def _write_run_artifacts(run_dir: Path, report: SearchOptimizeReport) -> None:
    run = report.run
    (run_dir / "run.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "frontier.json").write_text(run.frontier.model_dump_json(indent=2), encoding="utf-8")
    lineage = {candidate.id: candidate.parent_ids for candidate in run.candidates}
    (run_dir / "lineage.json").write_text(json.dumps(lineage, indent=2), encoding="utf-8")
    (run_dir / "search-memory.json").write_text(run.search_memory.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
