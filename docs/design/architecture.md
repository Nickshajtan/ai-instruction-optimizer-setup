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
ai_doc.providers    provider-neutral external semantic command boundary
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

## Optimization Flow

Semantic evaluation and production semantic adapters are part of the causal search path when configured.

```text
baseline snapshot + static baseline report + EvaluationSuite
        |
        v
deterministic + optional semantic invariant discovery
        |
        v
deterministic or semantic candidate generation
        |
        v
optional eligible prompt suboptimization
        |
        v
Tier-0 static/invariant safety gate
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

## Production Semantic Boundary

Adaptive modes can use the provider-neutral `AI_DOC_SEMANTIC_COMMAND` contract. The command receives JSON on stdin and returns normalized semantic data plus usage telemetry on stdout. Provider SDK objects therefore remain outside optimizer domain models.

The production stack can supply:

- semantic candidate generation;
- semantic invariant discovery and verification;
- semantic scenario evaluation;
- eligible prompt suboptimization.

Deterministic generation and offline operation remain first-class. `conservative` mode intentionally remains deterministic even if a semantic command is configured.

The production boundary is real, but the remaining v0.3 specification still contains acceptance hardening for CLI wiring, budget enforcement, and contradiction-safe invariant verification. Do not infer completion from the existence of an adapter alone.

## Evaluation Is Causal

`SearchController` consumes the repository `EvaluationSuite`. Semantic evaluation is not merely attached to the final report.

When an evaluator is configured, candidates that survive safety gates are evaluated against repository-owned scenarios. A required semantic failure can reject the candidate. Evaluation score contributes to the reliability objective. Failed evaluation evidence can be converted into feedback and used when generating a repair child.

Normal CI uses deterministic fake semantic providers/evaluators rather than paid calls.

## Effective Context Boundary

Evaluation does not concatenate every Markdown file in the repository.

`ai_doc.evaluators.context` separates the full corpus from always-loaded instructions and task-selected references. The deterministic selector now requires task-relevant explicit routing from already reachable context; merely sharing task vocabulary with a target reference is not enough to select it.

`ScenarioContextEvaluator` evaluates scenarios independently and retains effective-context evidence per scenario. Repair coverage verifies that useful extraction/context saving can survive while routing is restored.

This is deliberately an approximation of coding-agent loading behavior, not a claim to perfectly simulate Claude, Codex, Copilot, or future agents.

## Invariant Safety

Critical behavior has deterministic and semantic layers.

Deterministic extraction protects explicit normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN. A configured production semantic service can additionally discover high-confidence critical behavior without those keywords and verify meaning-preserving rewrites.

Semantic decisions can represent preserved, weakened, removed, and uncertain behavior and are persisted as candidate evidence.

A remaining v0.3 safety gap is contradiction handling: literal survival of the original critical sentence currently short-circuits semantic verification, so an opposing exception elsewhere can evade the semantic check. The remaining-work specification requires this to be fixed before the milestone is complete.

Semantic discovery also still needs stronger persisted rationale/provenance and negative coverage against overclassifying ordinary descriptive text.

## Candidate Generation

Deterministic candidate strategies remain cheap, reproducible, and offline-capable.

When the production semantic command is configured in an adaptive mode, `ProviderSemanticCandidateGenerator` can receive documents, invariants, strategy, previous summaries, explored transformations/fingerprints, structured feedback, and search memory. Its rendered documents enter the same safety/evaluation/Pareto pipeline as deterministic candidates.

The remaining acceptance work is to exercise this through the actual CLI stack and prove that meaningful feedback/search-memory changes are observable by the production adapter, rather than merely proving that injectable classes compose.

## Feedback And Repair

Feedback is derived from candidate evidence. Failed evaluation cases, invariant/static problems, and comparison information can become structured `OptimizationFeedback`.

A repair child is a normal candidate and must pass the same safety and semantic evaluation path. Candidate evidence persists the feedback used to produce the child. Integration coverage also verifies that a router repair can retain the useful parent context saving and keep extracted detail reachable.

## Pareto And Recommendation

The optimizer keeps clarity, reliability, critical invariant recall, always-loaded tokens, expected context tokens, and estimated context cost as separate dimensions where evidence exists.

The baseline is a real frontier competitor. A generated candidate is not recommended merely because it remains inside configured tolerances: the recommendation policy also requires material improvement. A legitimate no-change result is therefore supported and covered.

Missing semantic reliability remains unavailable rather than being fabricated from another metric.

Run-level recommendation/no-change reasons are persisted. Remaining v0.3 explainability work is to make those reasons concrete enough to identify the objective improvements, tolerances, or blocking factors without recomputing the policy.

## Cost And Budget Model

The domain separates deterministic operations, generation requests, evaluation requests, and prompt-suboptimizer requests. Normalized provider usage can include input/output tokens, USD cost, cache hits, and cost provenance.

The production CLI wraps semantic work with `BudgetedSemanticProvider`, so external request usage is bounded between provider calls. The current CLI wiring passes the request limit but does not yet pass the active input-token, output-token, and USD limits into that wrapper. Search-level accounting can stop later work after usage is observed, but this is weaker than provider-boundary enforcement.

Until the remaining budget work is complete, do not describe token/USD limits as strict pre-call guarantees. A provider that cannot estimate a call before execution may report an overrun after that call; the required behavior is then to persist it truthfully and stop subsequent external work.

## GEPA / Prompt Suboptimization

Prompt suboptimization remains behind `PromptSubOptimizer`. An eligible Markdown artifact is explicitly marked with `<!-- ai-doc:gepa -->`.

With GEPA enabled and a production semantic provider configured, an eligible artifact can be optimized and the changed text enters the ordinary candidate safety/evaluation/Pareto path. Usage is accounted separately. Ineligible/no-provider cases remain explicit no-ops rather than pretending optimization occurred.

The remaining v0.3 gap is adversarial acceptance coverage proving that a harmful GEPA rewrite is rejected by the common gates.

## Lexical And Optional Evaluator Adapters

Promptfoo is isolated in `ai_doc.evaluators.promptfoo`. Echo/contains behavior is lexical evidence, not semantic evidence, and scenario assertions remain isolated.

DeepEval is isolated in `ai_doc.evaluators.deepeval`. Imports remain optional. When no candidate is supplied, it evaluates baseline documentation rather than an empty snapshot.

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
candidates/<id>/evidence.json
candidates/<id>/diff.patch
```

Current evidence includes candidate content/proposal, lineage, evaluation, frontier/search state, repair feedback, invariant decisions, effective context, usage, status/rejection reasons, and run-level recommendation/no-change reasoning.

The remaining explainability work is narrower: semantic invariant discovery needs stronger provenance/rationale, and recommendation/no-change evidence should expose concrete policy factors instead of only a generic outcome label.

## Public API Boundary

Extensions should import only from:

```python
from ai_doc.api.v1 import AnalysisContext, Finding
```

Do not import optimizer/evaluator/provider internals from project extensions unless they are explicitly added to a future public API.

## Runtime Modes

`doctor` reports the runtime mode where practical:

- source checkout;
- installed package;
- standalone executable.

## Where To Read Next

For operational usage and examples, read [Semantic Optimization](../guides/semantic-optimization.md). For the authoritative list of unfinished semantic-core work, read [`../../specs/semantic-optimizer-core-v0.3.md`](../../specs/semantic-optimizer-core-v0.3.md).