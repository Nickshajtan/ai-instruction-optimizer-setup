# Architecture

`ai-doc` is structured as a CLI-oriented tool with stable black-box contracts and replaceable internal adapters.

Use this page when changing code boundaries, adding integrations, or deciding whether something is public API. For operational behavior, read [Semantic Optimization](../guides/semantic-optimization.md).

## Primary Contracts

Stable public contracts are the CLI and documented options, exit codes, JSON output schemas, `.ai-doc.yaml`, project-local extension registration, and explicit exports from `ai_doc.api.v1`. Optimizer/search/provider implementation details remain internal.

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

## Optimization Flow

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

Adaptive modes can use the provider-neutral `AI_DOC_SEMANTIC_COMMAND` contract. The command receives JSON on stdin and returns normalized semantic data plus usage telemetry on stdout. Provider SDK objects remain outside optimizer domain models.

The normal CLI stack wires the command provider through `BudgetedSemanticProvider` and can supply semantic candidate generation, invariant discovery/verification, scenario evaluation, and eligible prompt suboptimization. Deterministic generation and `conservative` mode remain offline-capable.

Production acceptance coverage verifies this CLI stack construction rather than only injecting adapter classes directly into `SearchController`. Feedback and search-memory contents are serialized into semantic generation requests.

## Effective Context Boundary

`ai_doc.evaluators.context` separates the full corpus from always-loaded instructions and task-selected references. The deterministic selector requires task-relevant explicit routing from already reachable context; merely sharing task vocabulary with a target reference is not enough to select it.

`ScenarioContextEvaluator` evaluates scenarios independently and retains effective-context evidence per scenario. This is an approximation of coding-agent loading behavior, not a claim to perfectly simulate Claude, Codex, Copilot, or future agents.

## Invariant Safety

Critical behavior has deterministic and semantic layers. Deterministic extraction protects explicit normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN. A configured semantic service can discover high-confidence implicit critical behavior and verify candidate meaning.

Semantic critical discoveries require confidence plus evidence and rationale, and retain discovery source/provenance. Ordinary descriptive provider results are not promoted to hard constraints solely because they are domain-related.

When semantic verification is configured, exact literal survival is not a safety short-circuit. The verifier still evaluates the candidate globally, allowing a retained MUST sentence plus a contradictory exception elsewhere to become weakened/uncertain and reject the candidate. Offline operation retains deterministic literal protection without pretending to detect semantic contradiction.

## Candidate Generation And Repair

Deterministic strategies remain cheap and reproducible. Production semantic generation receives documents, invariants, strategy, previous summaries, explored transformations, structured feedback, and search memory. Rendered output enters the common safety/evaluation/Pareto path.

Feedback is derived from candidate evidence. A repair child is a normal candidate and must pass the same gates and semantic evaluation. Persisted evidence keeps the feedback that produced the child.

## Pareto And Recommendation

Clarity, reliability, critical invariant recall, always-loaded tokens, expected context tokens, and estimated context cost remain separate dimensions where evidence exists. Missing semantic reliability is unavailable rather than fabricated.

The baseline is a real frontier competitor. Recommendation requires material improvement in at least one objective in addition to configured reliability/clarity tolerances. Selected-candidate evidence names improved objectives and tolerated regressions; no-change baseline evidence records concrete blocking factors.

## Cost And Budget Model

The domain separates deterministic operations, generation requests, evaluation requests, and prompt-suboptimizer requests. Normalized provider usage includes input/output tokens, USD cost, cache hits, and cost provenance where reported.

The production CLI passes request, input-token, output-token, and USD limits into `BudgetedSemanticProvider`. Accumulated reported usage prevents a later external invocation once a limit is reached. Search-level accounting independently stops later candidate work from the persisted usage totals.

Token/USD limits are not described as strict reservations for an unknowable future provider call. Without a trustworthy pre-call estimate, one call may report an overrun; that usage remains part of the run and no subsequent external work should begin after the limit is known.

Deterministic operations consume zero external usage.

## GEPA / Prompt Suboptimization

Prompt suboptimization remains behind `PromptSubOptimizer`. An eligible Markdown artifact is explicitly marked with `<!-- ai-doc:gepa -->`. Its output enters the same invariant/evaluation/Pareto path as other mutations; there is no GEPA safety bypass. Acceptance coverage includes a harmful GEPA rewrite rejected by the common critical-invariant gate. Ineligible/no-provider cases remain truthful no-ops.

## Lexical And Optional Evaluator Adapters

Promptfoo remains isolated in `ai_doc.evaluators.promptfoo`; echo/contains behavior is lexical evidence, not semantic evidence, and scenario assertions are isolated. DeepEval remains optional and evaluates baseline documentation when no candidate is supplied.

## Run Evidence

The optimizer writes:

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

Evidence includes candidate content/proposal, lineage, evaluation, frontier/search state, repair feedback, invariant decisions, effective context, provider usage, status/rejection reasons, and recommendation/no-change explanation. Semantic invariant discoveries retain provenance/rationale used to justify their critical classification.

## Public API Boundary

Extensions should import only documented public exports such as:

```python
from ai_doc.api.v1 import AnalysisContext, Finding
```

Do not import optimizer/evaluator/provider internals from project extensions unless they are explicitly added to a future public API.

## Where To Read Next

For operational usage, read [Semantic Optimization](../guides/semantic-optimization.md). While v0.3 remains open, [`../../specs/semantic-optimizer-core-v0.3.md`](../../specs/semantic-optimizer-core-v0.3.md) is the authoritative remaining-work/acceptance document.
