# Semantic Optimization

This guide explains the production behavior of `ai-doc optimize`. Agent-specific review procedure lives in `.ai/skills/semantic-optimization-review/SKILL.md`.

## Mental Model

The baseline remains a real Pareto competitor. Candidates are generated into an isolated output tree, pass deterministic Tier-0 safety gates, optionally pass semantic scenario evaluation, and are recommended only when the recommendation policy has evidence for preferring them. No generated candidate is required to win.

The causal path is:

```text
baseline -> deterministic + semantic invariant discovery
         -> deterministic or semantic generation
         -> Tier 0 static/invariant gates
         -> task-selected semantic evaluation
         -> evidence-backed objectives
         -> Pareto + feedback/repair
         -> recommendation or no-change
```

Tier-0 rejection occurs before semantic evaluation. Deterministic work remains available without any external provider and consumes no external request/token/USD budget.

## Production Semantic Provider

Adaptive `balanced` and `search` modes can use a provider-neutral production semantic adapter. Set `AI_DOC_SEMANTIC_COMMAND` to a command that reads one JSON request from stdin and writes one JSON response to stdout. This keeps provider SDK objects out of optimizer domain models and lets a team wrap OpenAI, Anthropic, Bedrock, a local model, or another provider without coupling the core package to that SDK.

Requests have this envelope:

```json
{"operation": "generate_candidate", "payload": {}}
```

Responses have this envelope:

```json
{
  "data": {},
  "usage": {
    "requests": 1,
    "input_tokens": 100,
    "output_tokens": 20,
    "cost_usd": "0.002",
    "cost_source": "provider",
    "cache_hits": 0
  }
}
```

Supported operations are `generate_candidate`, `discover_invariants`, `verify_invariant`, `evaluate`, and `optimize_prompt`. The repository test fixture exercises this exact production command adapter without network calls.

When the command is configured, adaptive semantic generation receives the current documents, invariants, strategy, previous candidate summaries, explored fingerprints, parent feedback, and search memory. The response returns the normal candidate proposal plus rendered documents, so semantic output goes through the same safety, evaluation, Pareto, and artifact pipeline as deterministic output.

`conservative` intentionally remains deterministic/offline even when the environment variable exists.

## Invariant Safety

Critical behavior has two complementary layers. Literal extraction protects explicit normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN. The configured semantic service can additionally discover high-confidence critical behavior that lacks those keywords.

Semantic discoveries are accepted as critical only when the provider classifies them as critical with confidence at least `0.8`; this prevents every descriptive sentence from automatically becoming a hard invariant. Candidate verification records `preserved`, `weakened`, `removed`, or `uncertain`. Only preserved critical behavior passes. Literal preservation is recorded separately from semantic preservation.

## Semantic Evaluation And Effective Context

`--deep` evaluates scenarios independently. When `AI_DOC_SEMANTIC_COMMAND` is configured, the same production provider contract performs semantic evaluation; otherwise the optional DeepEval adapter remains available.

Evaluation uses task-selected effective context rather than blindly concatenating the repository. Instruction and skill documents are always-loaded. Reference documents become reachable through explicit, task-relevant routes from already-reachable context. Merely sharing task vocabulary with a target document is not sufficient.

This is deliberately still an approximation of agent loading behavior, not a claim to perfectly simulate Claude, Codex, Copilot, or every future agent.

## Feedback And Repair

A semantic failure can become structured feedback for a child candidate. The child is generated from the parent state, re-evaluated, and independently compared on the frontier. Persisted candidate evidence records the feedback that caused the repair, so the causal chain can be inspected after the run rather than reconstructed from logs.

A repaired router must keep extracted detail reachable while preserving the useful context saving; semantic success alone is not permission to restore all detail to always-loaded context.

## Telemetry And Budgets

External work is accounted separately as generation, evaluation, and prompt-suboptimizer requests. Usage also tracks input tokens, output tokens, USD cost, cache hits, and whether cost was provider-reported or estimated by the adapter.

`max_llm_requests`, `max_input_tokens`, `max_output_tokens`, and `max_cost_usd` stop additional external work when accumulated usage reaches the configured limit. Deterministic operations remain zero external usage. The command adapter is responsible for returning truthful provider usage or an explicitly identified estimate.

## GEPA

GEPA remains a prompt suboptimizer, not the outer search algorithm. A Markdown document is explicitly eligible for prompt suboptimization when it contains:

```html
<!-- ai-doc:gepa -->
```

With GEPA enabled, a configured production semantic provider, and an eligible artifact, `optimize_prompt` is invoked. Its changed text becomes part of the candidate and then passes the normal invariant, evaluation, budget, Pareto, and recommendation gates. A GEPA regression can therefore be rejected exactly like another candidate regression.

If no eligible artifact/provider exists, the run records an explicit no-op reason instead of claiming that prompt optimization occurred.

## Evidence And Artifacts

A run writes `run.json`, `report.json`, `frontier.json`, `lineage.json`, and `search-memory.json`. Each generated candidate contains its rendered tree, `proposal.json`, `diff.patch`, `evaluation.json`, and `evidence.json`.

`evidence.json` records generation rationale, repair feedback when present, invariant decisions, and effective-context paths. `run.json`/`report.json` include normalized telemetry and an explicit recommendation/no-change reason. This is intended to answer why a candidate was generated, what safety/evaluation evidence it had, what external work it consumed, and why it was or was not selected without rerunning the optimizer.

For the repeatable agent review procedure, use `.ai/skills/semantic-optimization-review/SKILL.md`.

## Current Scope

Semantic Core v0.3 now has production execution paths for semantic generation, semantic invariant discovery/verification, usage telemetry, eligible GEPA suboptimization, persisted semantic evidence, and hardened explicit-route context selection. The provider-neutral command boundary intentionally does not prescribe a hosted vendor SDK.

This milestone still does not claim perfect agent simulation, autonomous application of generated patches, or universal model-provider support. Those are outside the v0.3 scope rather than hidden incomplete capabilities.
