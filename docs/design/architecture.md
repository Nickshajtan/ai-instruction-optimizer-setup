# Architecture

`ai-doc` is structured as a CLI-oriented tool with stable black-box contracts and
replaceable internal adapters.

Use this page when you are changing code boundaries, adding integrations, or deciding
whether something is public API. If you only want to run the tool, start with
[Getting Started](../guides/getting-started.md).

## Reading This Page

The main design idea is separation. Users interact with stable command-line, JSON,
configuration, and extension contracts. Internals can change as long as those contracts
keep working.

Terms used below:

- CLI: the `ai-doc` command and its subcommands.
- Domain model: a typed Python object used by core logic and reports.
- Adapter: code that translates between `ai-doc` and an optional external tool.
- Snapshot: the parsed set of Markdown documents for one project or candidate.
- Candidate: a proposed rewritten documentation tree stored for review.
- Pareto frontier: the set of candidates where no candidate is strictly better on every
  tracked objective.

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
ai_doc.domain       stable domain schemas
ai_doc.discovery    Markdown file discovery
ai_doc.markdown     Markdown parsing, links, and graph construction
ai_doc.analyzers    deterministic static analyzers
ai_doc.tokens       token counting and pricing helpers
ai_doc.evaluators   Promptfoo and DeepEval adapter boundaries
ai_doc.optimizer    candidate generation, Pareto search, feedback, artifacts
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

In plain terms, `check` loads configuration, merges nested module configs when no explicit
`--config` file was passed, finds Markdown files, parses them, runs deterministic
analyzers, optionally runs the configured deep evaluator, and returns a human or JSON
report.

## Optimization Flow

```text
baseline snapshot
  -> static baseline report
  -> invariant extraction
  -> candidate generation
  -> isolated candidate tree
  -> Tier 0 static gate
  -> objective vector
  -> Pareto frontier
  -> optional feedback-directed children
  -> recommendation
  -> run artifacts
```

The optimizer writes under `.ai-doc-output/<run-id>/` and does not modify source
documentation.

This isolation is deliberate. Users should be able to inspect candidate files and
patches before deciding whether any change belongs in the target project.

## Pareto Selection

The optimizer keeps clarity, reliability, critical invariant recall, and context cost as
separate dimensions. It does not use one weighted scalar score as the frontier mechanism.

A candidate dominates another candidate only when it is no worse in every required
objective and strictly better in at least one objective, after configured tolerances.

The baseline participates in frontier comparison so the report never implies improvement
when all generated candidates are worse.

## Adapter Boundaries

Promptfoo is isolated in `ai_doc.evaluators.promptfoo`. It is discovered with
runtime dependency checks, invoked as a subprocess with `shell=False`, and normalized to
internal evaluation schemas.

DeepEval is isolated in `ai_doc.evaluators.deepeval`. Imports are optional and happen
inside the adapter, so static operation does not require DeepEval.

GEPA is isolated behind `PromptSubOptimizer` in `ai_doc.optimizer.prompt_suboptimizer`.
DeepEval `Prompt`, `PromptOptimizer`, `GEPA`, and `Golden` objects do not cross that
boundary.

## Public API Boundary

Extensions should import only from:

```python
from ai_doc.api.v1 import AnalysisContext, Finding
```

Do not import from `ai_doc.optimizer`, `ai_doc.markdown`, `ai_doc.evaluators`, or other
internal modules in project extensions.

## Runtime Modes

`doctor` reports the runtime mode where practical:

- source checkout;
- installed package;
- standalone executable.

This distinction helps debug `.tools/ai-doc` deployments and PyInstaller builds.
