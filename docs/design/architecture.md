# Architecture

`ai-doc` is structured as a CLI-oriented tool with stable black-box contracts and replaceable internal adapters.

Use this page when you are changing code boundaries, adding integrations, or deciding whether something is public API. If you only want to run the tool, start with [Getting Started](../guides/getting-started.md). For a detailed human explanation of the optimizer itself, read [Semantic Optimization](../guides/semantic-optimization.md).

## Reading This Page

The main design idea is separation. Users interact with stable command-line, JSON, configuration, and extension contracts. Internals can change as long as those contracts keep working.

Terms used below:

- CLI: the `ai-doc` command and its subcommands.
- Domain model: a typed Python object used by core logic and reports.
- Adapter: code that translates between `ai-doc` and an optional external tool.
- Snapshot: the parsed set of Markdown documents for one project or candidate.
- Candidate: a proposed rewritten documentation tree stored for review.
- Evaluation suite: repository-owned task scenarios used to check required/forbidden behavior.
- Effective context: the subset of documentation selected for one evaluation task rather than the whole repository corpus.
- Pareto frontier: candidates where no candidate is strictly better on every tracked comparable objective.

## Primary Contracts

Stable public contracts:

- CLI commands and documented options.
- Exit codes.
- JSON output schemas.
- `.ai-doc.yaml` configuration schema.
- Project-local extension registration.
- Explicit exports from `ai_doc.api.v1`.

Internal and unstable:

- optimizer implementation details;
- Promptfoo adapter internals;
- DeepEval adapter internals;
- Markdown parser implementation;
- candidate storage/cache internals beyond documented run output files;
- search orchestration internals.

## Package Map

```text
ai_doc.cli          Typer commands and CLI-only concerns
ai_doc.config       Pydantic config models and YAML loading
ai_doc.domain       typed domain schemas
ai_doc.discovery    Markdown file discovery
ai_doc.markdown     Markdown parsing, links, and graph construction
ai_doc.analyzers    deterministic static analyzers
ai_doc.tokens       token counting and pricing helpers
ai_doc.evaluators   lexical/semantic evaluator and context-selection boundaries
ai_doc.optimizer    generation, gates, feedback, Pareto search, artifacts
ai_doc.plugins      project-local static analyzer extension loading and registry
ai_doc.api.v1       stable extension imports
ai_doc.reporting    console and JSON report rendering
```

## Check Flow

```text
CLI
  -> root discovery
  -> config load and nested config merge
  -> extension load for custom static analyzers
  -> Markdown discovery
  -> Markdown parse
  -> document graph
  -> static analyzers
  -> context-cost calculation
  -> optional deep evaluation
  -> report
```

Static mode never requires Promptfoo, DeepEval, or API keys.

In plain terms, `check` loads configuration, merges nested module configs when no explicit `--config` file was passed, finds Markdown files, parses them, runs deterministic analyzers, optionally runs the configured deep evaluator, and returns a human or JSON report.

## Optimization Flow

The optimizer is no longer only a static candidate generator followed by Pareto scoring. When semantic evaluation is configured, evaluation evidence is part of the search loop and can cause rejection and feedback-directed repair.

```text
baseline snapshot + static baseline report + EvaluationSuite
        |
        v
extract deterministic invariants
        |
        v
generate candidate
        |
        v
Tier-0 static/invariant gate
        |
        +---- failure ----> reject
        |
        v
optional per-scenario semantic evaluation
        |
        +---- failure ----> reject + structured feedback
        |                         |
        |                         v
        |                    repair child
        |                         |
        |                         +----> same gates/evaluation
        v
objective vector
        |
        v
baseline-aware Pareto frontier
        |
        v
recommendation policy may choose candidate or no change
        |
        v
run artifacts
```

The optimizer writes under `.ai-doc-output/<run-id>/` and does not modify source documentation.

This isolation is deliberate. Users should be able to inspect candidate files and patches before deciding whether any change belongs in the target project.

## Evaluation Is Causal

`SearchController` consumes the repository `EvaluationSuite`. Semantic evaluation is not merely attached to the final report.

When an evaluator is configured, candidates that survive deterministic gates are evaluated against repository-owned scenarios. A required semantic failure can reject the candidate. Evaluation score contributes to the reliability objective. Failed evaluation evidence can be converted into feedback and used when generating a repair child.

The end-to-end integration coverage intentionally proves this chain with a deterministic fake semantic evaluator so normal CI does not require paid calls.

## Effective Context Boundary

Evaluation does not have to concatenate every Markdown file in the repository.

`ai_doc.evaluators.context` provides a context-selection boundary that separates the full documentation corpus from always-loaded instructions and task-selected references. The current implementation is deterministic and approximate: it uses document profiles, task terms, and references to select relevant context.

`ScenarioContextEvaluator` evaluates scenarios independently and passes the selected context for each scenario to the wrapped semantic evaluator. Effective-context evidence is retained in the normalized evaluation summary.

This boundary is necessary for FinOps optimization. Moving large low-frequency detail out of an always-loaded instruction file only helps if relevant tasks can still discover the extracted document.

The selector is intentionally not claimed to perfectly simulate every coding agent. Routing/discoverability anti-gaming remains active hardening work.

## Invariant Safety

The production Tier-0 path protects explicit critical normative language with deterministic invariant extraction and verification. This catches obvious removal of rules such as MUST/NEVER instructions before semantic evaluation.

A semantic invariant-verification boundary also exists and can represent preserved, weakened, removed, and uncertain results. Unit tests prove the seam can accept a meaning-preserving paraphrase and reject weakening.

A concrete semantic invariant discovery/verifier is not yet wired into the normal production CLI path. Therefore the semantic boundary is architecture, while deterministic explicit-rule protection is the current production behavior. See the remaining-work specification before treating implicit critical behavior as fully protected.

## Candidate Generation Boundary

Deterministic candidate strategies remain first-class because they are cheap, reproducible, and work without model access.

The optimizer also exposes a semantic generation boundary capable of receiving previous candidate summaries, explored transformations, feedback, search memory, invariants, and strategy. Tests prove these values reach an injected semantic generator.

The normal CLI does not yet wire a production semantic generator. Adaptive search therefore means bounded/iterative search over currently available mutations; it should not yet be read as a promise that an LLM is generating arbitrary semantic rewrites.

## Feedback And Repair

Feedback is derived from candidate evidence rather than being only a test fixture. Failed evaluation cases, invariant/static problems, and comparison information can become structured `OptimizationFeedback`.

The current repair path can use evaluation feedback to strengthen a weak router while retaining useful parent changes. The child is a normal candidate: it is sent through the same deterministic gates and semantic evaluation rather than being trusted merely because it is a repair.

## Pareto Selection

The optimizer keeps clarity, reliability, critical invariant recall, always-loaded tokens, expected context tokens, and estimated context cost as separate dimensions where evidence exists. It does not use one weighted scalar score as the frontier mechanism.

A candidate dominates another candidate only when it is no worse in every comparable objective and strictly better in at least one objective, after configured tolerances.

The baseline participates in frontier comparison so the report never needs to imply improvement when generated candidates are worse. The recommendation policy may return no candidate.

Missing semantic reliability is represented as unavailable rather than automatically substituted with invariant recall.

## Cost Model

The domain separates deterministic operations, generation requests, evaluation requests, and prompt-suboptimizer requests. Deterministic work does not consume the LLM-request budget.

The cost model also has fields for input/output tokens and USD cost. These are not yet fully populated by all production external adapters. Request accounting is therefore more mature than token/USD accounting. Full provider telemetry and truthful cost/token enforcement are remaining milestone work.

## Adapter Boundaries

Promptfoo is isolated in `ai_doc.evaluators.promptfoo`. The current echo/contains behavior is classified as lexical rather than semantic evidence. Scenario assertions are built independently so one scenario's requirements do not leak into another.

DeepEval is isolated in `ai_doc.evaluators.deepeval`. Imports are optional and happen inside the adapter, so static operation does not require DeepEval. When no candidate is supplied, the adapter evaluates baseline documentation rather than an empty snapshot.

GEPA is isolated behind `PromptSubOptimizer` in `ai_doc.optimizer.prompt_suboptimizer`. DeepEval `Prompt`, `PromptOptimizer`, `GEPA`, and `Golden` objects do not cross that boundary.

GEPA currently has truthful no-op behavior when no eligible prompt artifact is wired. Behaviorally effective eligible-artifact integration remains unfinished.

## Run Evidence

The optimizer writes reviewable artifacts including:

```text
run.json
frontier.json
lineage.json
search-memory.json
report.json
candidates/<id>/proposal.json
candidates/<id>/candidate/...
candidates/<id>/evaluation.json
candidates/<id>/diff.patch
```

These already preserve candidate content, proposal, lineage, evaluation, frontier, and run/search state. The remaining evidence work is to persist richer feedback provenance, semantic invariant decisions, recommendation/no-change reasoning, and complete external token/USD telemetry.

## Public API Boundary

Extensions should import only from:

```python
from ai_doc.api.v1 import AnalysisContext, Finding
```

Do not import from `ai_doc.optimizer`, `ai_doc.markdown`, `ai_doc.evaluators`, or other internal modules in project extensions.

## Runtime Modes

`doctor` reports the runtime mode where practical:

- source checkout;
- installed package;
- standalone executable.

This distinction helps debug `.tools/ai-doc` deployments and PyInstaller builds.

## Where To Read Next

For operational usage and examples, read [Semantic Optimization](../guides/semantic-optimization.md). For the authoritative list of unfinished semantic-core implementation work, read [`../../specs/semantic-optimizer-core-v0.3.md`](../../specs/semantic-optimizer-core-v0.3.md).