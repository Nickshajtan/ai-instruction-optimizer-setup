from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ai_doc.app import load_suite, run_static_check
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.config.search import OptimizeMode, RuntimeSearchConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.evaluations import Evaluator
from ai_doc.evaluators.context import ScenarioContextEvaluator
from ai_doc.evaluators.deepeval import DeepEvalEvaluator, DeepEvalUnavailableError
from ai_doc.optimizer.generator import SemanticCandidateGenerator
from ai_doc.optimizer.invariants import SemanticInvariantDiscoverer, SemanticInvariantVerifier
from ai_doc.optimizer.prompt_suboptimizer import PromptSubOptimizer
from ai_doc.optimizer.search import SearchController
from ai_doc.optimizer.semantic import (
    ProviderPromptSubOptimizer,
    ProviderSemanticCandidateGenerator,
    ProviderSemanticEvaluator,
    ProviderSemanticInvariantService,
)
from ai_doc.plugins.loader import ExtensionError, load_extensions
from ai_doc.providers.semantic import (
    SEMANTIC_COMMAND_ENV,
    BudgetedSemanticProvider,
    CommandSemanticProvider,
    SemanticProvider,
)
from ai_doc.reporting.console import render_search_optimize_console
from ai_doc.reporting.json import render_json
from ai_doc.reporting.models import SearchOptimizeReport
from ai_doc.root import discover_project_root
from ai_doc.tokens.counter import ApproximateTokenCounter


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
    prompt_suboptimizer: PromptSubOptimizer | None = None


def optimize_command(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    path: Annotated[Path, typer.Argument(help="Repository root to optimize.")] = Path("."),
    root: Annotated[Path | None, typer.Option("--root", help="Explicit project root.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="Path to .ai-doc.yaml.")] = None,
    output_format: Annotated[OutputFormat, typer.Option("--format", help="Output format.")] = OutputFormat.CONSOLE,
    output: Annotated[Path, typer.Option("--output", help="Output directory.")] = Path(".ai-doc-output"),
    candidates: Annotated[int | None, typer.Option("--candidates", help="Initial candidates.")] = None,
    generations: Annotated[int | None, typer.Option("--generations", help="Search generations.")] = None,
    max_candidates: Annotated[
        int | None, typer.Option("--max-candidates", help="Maximum generated candidates.")
    ] = None,
    max_cost: Annotated[float | None, typer.Option("--max-cost", help="Maximum optimizer cost USD.")] = None,
    max_requests: Annotated[
        int | None, typer.Option("--max-requests", help="Maximum external model requests.")
    ] = None,
    strategy: Annotated[OptimizeMode | None, typer.Option("--strategy", help="Optimization mode.")] = None,
    deep: Annotated[
        bool, typer.Option("--deep", help="Run semantic evaluation on task-selected context.")
    ] = False,
    gepa: Annotated[bool, typer.Option("--gepa", help="Enable GEPA prompt sub-optimizer.")] = False,
    seed: Annotated[int | None, typer.Option("--seed", help="Random seed.")] = None,
    show_frontier: Annotated[
        bool, typer.Option("--show-frontier", help="Print all frontier candidates.")
    ] = False,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Do not prompt before external calls.")
    ] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Keep adapter temporary files.")] = False,
    experimental_gepa: Annotated[
        bool, typer.Option("--experimental-gepa", help="Alias for --gepa.")
    ] = False,
) -> None:
    project_root = discover_project_root(path, root)
    try:
        loaded = load_config(project_root, config)
        extensions = load_extensions(project_root, loaded.extensions, debug=debug)
        baseline_report = run_static_check(project_root, loaded, extensions=extensions)
        baseline_snapshot = discover_markdown(project_root, loaded, ApproximateTokenCounter())
    except (ConfigError, ExtensionError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    runtime = RuntimeSearchConfig(
        mode=strategy or loaded.optimization.strategy,
        population=loaded.optimization.population.model_copy(deep=True),
        search=loaded.optimization.search.model_copy(deep=True),
        pareto=loaded.optimization.pareto.model_copy(deep=True),
        gepa=loaded.optimization.gepa.model_copy(
            update={"enabled": gepa or experimental_gepa or loaded.optimization.gepa.enabled}
        ),
        recommendation=loaded.optimization.recommendation.model_copy(deep=True),
        exploration_rate=loaded.optimization.exploration_rate,
        restart_after_stagnation=loaded.optimization.restart_after_stagnation,
        concurrency=loaded.optimization.concurrency,
        seed=seed or loaded.optimization.gepa.random_seed,
    )
    _apply_overrides(runtime, candidates, generations, max_candidates, max_cost, max_requests)
    if runtime.mode == OptimizeMode.CONSERVATIVE:
        runtime.population.initial_candidates = 1
        runtime.search.max_candidates = 1
        runtime.search.generations = 1

    suite = load_suite(project_root)
    semantic = _build_semantic_stack(runtime, deep)
    if semantic.provider:
        typer.echo(
            f"Semantic provider enabled from {SEMANTIC_COMMAND_ENV}; generation and invariant safety are active.",
            err=True,
        )
    if deep:
        interaction = "non-interactive" if non_interactive else "interactive"
        typer.echo(f"Semantic evaluation enabled ({interaction}); external calls may occur.", err=True)

    output_root = (project_root / output).resolve() if not output.is_absolute() else output
    try:
        controller = SearchController(
            loaded,
            runtime,
            output_root,
            extensions=extensions,
            evaluator=semantic.evaluator,
            semantic_generator=semantic.generator,
            semantic_invariant_verifier=semantic.invariant_verifier,
            semantic_invariant_discoverer=semantic.invariant_discoverer,
            prompt_suboptimizer=semantic.prompt_suboptimizer,
        )
        result = controller.optimize(baseline_snapshot, suite, baseline_report)
    except (DeepEvalUnavailableError, RuntimeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    recommended = next(
        (candidate for candidate in result.run.candidates if candidate.id == result.run.recommended_candidate_id),
        None,
    )
    report = SearchOptimizeReport(
        baseline=baseline_report,
        run=result.run,
        candidates_evaluated=len([candidate for candidate in result.run.candidates if candidate.id != "baseline"]),
        candidates_rejected=len([candidate for candidate in result.run.candidates if candidate.status == "rejected"]),
        frontier=result.run.frontier.entries,
        recommended_candidate=recommended,
        baseline_in_frontier=bool(result.run.metadata.get("baseline_in_frontier")),
    )
    _write_run_artifacts(result.run_dir, report)
    rendered_report = (
        render_json(report)
        if output_format == OutputFormat.JSON
        else render_search_optimize_console(report, show_frontier=show_frontier)
    )
    typer.echo(rendered_report)
    raise typer.Exit(4 if not result.run.recommended_candidate_id else 0)


def _build_semantic_stack(runtime: RuntimeSearchConfig, deep: bool) -> SemanticStack:
    enabled = bool(os.getenv(SEMANTIC_COMMAND_ENV)) and runtime.mode != OptimizeMode.CONSERVATIVE
    if not enabled:
        evaluator = ScenarioContextEvaluator(DeepEvalEvaluator()) if deep else None
        return SemanticStack(evaluator=evaluator)
    provider = BudgetedSemanticProvider(CommandSemanticProvider(), runtime.search.max_llm_requests)
    invariant_service = ProviderSemanticInvariantService(provider)
    evaluator = ScenarioContextEvaluator(ProviderSemanticEvaluator(provider)) if deep else None
    return SemanticStack(
        provider=provider,
        generator=ProviderSemanticCandidateGenerator(provider),
        invariant_verifier=invariant_service,
        invariant_discoverer=invariant_service,
        evaluator=evaluator,
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
