# Semantic Optimization

This guide explains the production behavior of `ai-doc optimize`. Agent-specific review procedure lives in `.ai/skills/semantic-optimization-review/SKILL.md`.

## Mental Model

The baseline remains a real Pareto competitor. Candidates are generated into an isolated output tree, pass safety gates, optionally pass semantic scenario evaluation, and are recommended only when the recommendation policy has evidence for preferring them. No generated candidate is required to win, and merely staying within configured tolerances is not enough: a recommended candidate must materially improve at least one recommendation dimension.

The causal path is:

```text
baseline -> deterministic + optional semantic invariant discovery
         -> deterministic or semantic generation
         -> optional eligible prompt suboptimization
         -> Tier 0 static/invariant safety
         -> task-selected semantic evaluation
         -> evidence-backed objectives
         -> Pareto + feedback/repair
         -> recommendation or no-change
```

Deterministic work remains available without any external provider and consumes no external request/token/USD budget.

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

Supported operations are `generate_candidate`, `discover_invariants`, `verify_invariant`, `evaluate`, and `optimize_prompt`. The repository test fixture exercises this production command contract without network calls.

When the command is configured, adaptive semantic generation receives the current documents, invariants, strategy, previous candidate summaries, explored fingerprints, parent feedback, and search memory. The response returns the normal candidate proposal plus rendered documents, so semantic output goes through the same safety, evaluation, Pareto, and artifact pipeline as deterministic output.

`conservative` intentionally remains deterministic/offline even when the environment variable exists.

## Invariant Safety

Critical behavior has two complementary layers. Literal extraction protects explicit normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN. The configured semantic service can additionally discover high-confidence critical behavior that lacks those keywords.

Semantic discoveries are currently accepted as critical when the provider classifies them as critical with confidence at least `0.8`. Candidate verification can record `preserved`, `weakened`, `removed`, or `uncertain`; non-preserved critical behavior is rejected.

There is one important remaining v0.3 limitation: literal survival of an original critical sentence currently short-circuits semantic verification for that invariant. A contradictory exception elsewhere in the candidate can therefore evade the semantic contradiction check. Until that hardening is complete, human/agent review should inspect the candidate globally for conflicting exceptions rather than treating literal preservation as conclusive safety evidence.

Semantic discovery also still needs richer persisted rationale/provenance so a reviewer can inspect why provider-classified text became a critical invariant.

## Semantic Evaluation And Effective Context

`--deep` evaluates scenarios independently. When `AI_DOC_SEMANTIC_COMMAND` is configured, the same production provider contract performs semantic evaluation; otherwise the optional DeepEval adapter remains available.

Evaluation uses task-selected effective context rather than blindly concatenating the repository. Instruction and skill documents are always-loaded. Reference documents become reachable through explicit, task-relevant routes from already-reachable context. Merely sharing task vocabulary with a target document is not sufficient.

This is deliberately still an approximation of agent loading behavior, not a claim to perfectly simulate Claude, Codex, Copilot, or every future agent.

## Feedback And Repair

A semantic failure can become structured feedback for a child candidate. The child is generated from the parent state, re-evaluated, and independently compared on the frontier. Persisted candidate evidence records the feedback that caused the repair, so the causal chain can be inspected after the run rather than reconstructed from logs.

A repaired router must keep extracted detail reachable while preserving the useful context saving; semantic success alone is not permission to restore all detail to always-loaded context.

## Telemetry And Budgets

External work is accounted separately as generation, evaluation, and prompt-suboptimizer requests. Usage can also track input tokens, output tokens, USD cost, cache hits, and whether cost was provider-reported or estimated by the adapter.

The production semantic stack currently applies the external request limit at the provider boundary. Search-level accounting also observes token and USD usage and can stop later work after limits are reached.

Input-token, output-token, and USD limits are not yet all passed into the production provider budget wrapper. They should therefore be read as accumulated stop controls, not strict pre-call guarantees. A single provider call/candidate cycle can report usage beyond one of those limits before subsequent work is stopped. The remaining v0.3 work tightens this behavior and requires any unavoidable post-call overrun to be reported truthfully.

Deterministic operations remain zero external usage. The command adapter is responsible for returning truthful provider usage or an explicitly identified estimate.

## GEPA / Prompt Suboptimization

GEPA remains a prompt suboptimizer, not the outer search algorithm. A Markdown document is explicitly eligible for prompt suboptimization when it contains:

```html
<!-- ai-doc:gepa -->
```

With GEPA enabled, a configured production semantic provider, and an eligible artifact, `optimize_prompt` is invoked. Its changed text becomes part of the candidate and then passes the normal invariant, evaluation, Pareto, and recommendation pipeline. Usage is accounted separately.

If no eligible artifact/provider exists, the run records an explicit no-op reason instead of claiming that prompt optimization occurred.

The production path is wired; the remaining v0.3 acceptance gap is an adversarial test proving that a harmful GEPA rewrite is actually rejected by the common safety/evaluation gates.

## Evidence And Artifacts

A run writes `run.json`, `report.json`, `frontier.json`, `lineage.json`, and `search-memory.json`. Each generated candidate contains its rendered tree, `proposal.json`, `diff.patch`, `evaluation.json`, and `evidence.json`.

`evidence.json` records generation rationale, repair feedback when present, invariant decisions, and effective-context paths. `run.json`/`report.json` include normalized telemetry, status/rejection information, objectives, and a recommendation/no-change reason.

Most causal decisions can therefore be reconstructed without rerunning the optimizer. Two explainability areas remain intentionally called out by the v0.3 spec: semantic invariant discovery needs richer rationale/provenance, and recommendation/no-change reasoning should identify concrete objective/policy factors rather than only a generic outcome label.

For the repeatable agent review procedure, use `.ai/skills/semantic-optimization-review/SKILL.md`.

## Current Scope

Semantic Core v0.3 has production execution paths for semantic generation, semantic invariant discovery/verification, normalized usage telemetry, eligible prompt suboptimization, persisted semantic evidence, hardened explicit-route context selection, baseline-aware Pareto selection, and feedback-directed repair.

The milestone is still in hardening rather than complete: provider-boundary token/USD budgets, contradiction-safe critical invariants, semantic-discovery provenance, production CLI acceptance coverage, GEPA regression coverage, and richer recommendation explanation remain open in `specs/semantic-optimizer-core-v0.3.md`.

This milestone does not claim perfect agent simulation, autonomous application of generated patches, or universal model-provider support. Those are outside the v0.3 scope.
