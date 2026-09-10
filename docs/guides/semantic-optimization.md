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

Supported operations are `generate_candidate`, `discover_invariants`, `verify_invariant`, `evaluate`, and `optimize_prompt`. Repository tests exercise this production command contract without network calls.

When the command is configured, adaptive semantic generation receives the current documents, invariants, strategy, previous candidate summaries, explored fingerprints, parent feedback, and search memory. Feedback and search-memory contents are serialized into the production provider request, not represented only by placeholder booleans. Semantic output goes through the same safety, evaluation, Pareto, and artifact pipeline as deterministic output.

`conservative` intentionally remains deterministic/offline even when the environment variable exists.

## Invariant Safety

Critical behavior has two complementary layers. Literal extraction protects explicit normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN. The configured semantic service can additionally discover high-confidence critical behavior that lacks those keywords.

Semantic critical discoveries require confidence at least `0.8` plus evidence and rationale. Persisted invariants retain their discovery source, source location, evidence fragment, confidence, and rationale. Ordinary provider-returned descriptive statements are not promoted merely because they are domain-related.

Candidate verification records `preserved`, `weakened`, `removed`, or `uncertain`; non-preserved critical behavior is rejected. When semantic verification is configured, literal survival is evidence but not conclusive proof: the verifier still checks the candidate as a whole, so retaining the original MUST sentence while adding a contradictory exception can be rejected.

Without a semantic verifier, deterministic literal protection remains the offline fallback and cannot make claims about semantic contradictions elsewhere.

## Semantic Evaluation And Effective Context

`--deep` evaluates scenarios independently. When `AI_DOC_SEMANTIC_COMMAND` is configured, the same production provider contract performs semantic evaluation; otherwise the optional DeepEval adapter remains available.

Evaluation uses task-selected effective context rather than blindly concatenating the repository. Instruction and skill documents are always-loaded. Reference documents become reachable through explicit, task-relevant routes from already-reachable context. Merely sharing task vocabulary with a target document is not sufficient.

This is deliberately still an approximation of agent loading behavior, not a claim to perfectly simulate Claude, Codex, Copilot, or every future agent.

## Feedback And Repair

A semantic failure can become structured feedback for a child candidate. The child is generated from the parent state, re-evaluated, and independently compared on the frontier. Persisted candidate evidence records the feedback that caused the repair, so the causal chain can be inspected after the run rather than reconstructed from logs.

A repaired router must keep extracted detail reachable while preserving the useful context saving; semantic success alone is not permission to restore all detail to always-loaded context.

## Telemetry And Budgets

External work is accounted separately as generation, evaluation, and prompt-suboptimizer requests. Usage tracks input tokens, output tokens, USD cost, cache hits, and whether cost was provider-reported or estimated by the adapter.

The production semantic stack passes request, input-token, output-token, and USD limits to the provider budget wrapper. Once accumulated reported usage reaches a configured limit, another external invocation is not started. Search-level accounting uses the same limits to stop further candidate work.

Token and USD budgets are truthful accumulated controls, not a promise that an unknown provider call can always be predicted before it runs. If no trustworthy pre-call estimate exists, one provider call may report usage beyond the remaining token/USD budget. That reported overrun is retained and subsequent external work is blocked. Provider adapters should supply estimates only when they are trustworthy rather than pretending post-call accounting is a strict reservation system.

Deterministic operations remain zero external usage. The command adapter is responsible for returning truthful provider usage or an explicitly identified estimate.

## GEPA / Prompt Suboptimization

GEPA remains a prompt suboptimizer, not the outer search algorithm. A Markdown document is explicitly eligible for prompt suboptimization when it contains:

```html
<!-- ai-doc:gepa -->
```

With GEPA enabled, a configured production semantic provider, and an eligible artifact, `optimize_prompt` is invoked. Its changed text becomes part of the candidate and then passes the normal invariant, evaluation, Pareto, and recommendation pipeline. Usage is accounted separately.

There is no GEPA safety bypass: a harmful prompt rewrite can be rejected by the common critical-invariant or behavioral evaluation gates. If no eligible artifact/provider exists, the run records an explicit no-op reason instead of claiming that prompt optimization occurred.

## Evidence And Artifacts

A run writes `run.json`, `report.json`, `frontier.json`, `lineage.json`, and `search-memory.json`. Each generated candidate contains its rendered tree, `proposal.json`, `diff.patch`, `evaluation.json`, and `evidence.json`.

Candidate evidence records generation rationale, repair feedback when present, invariant decisions, effective-context paths, and recommendation reasoning when the candidate is selected. When no generated candidate qualifies, baseline evidence records concrete blocking factors for no-change. Recommendation explanations name material objective improvements and any tolerated reliability/clarity regression instead of only saying that a candidate was policy-qualified.

The artifacts are intended to support post-run review without rerunning the optimizer. Provider-neutral telemetry and semantic judgments are only as trustworthy as the provider contract supplying them, so reviewers should distinguish provider-reported evidence from deterministic facts.

For the repeatable agent review procedure, use `.ai/skills/semantic-optimization-review/SKILL.md`.

## Current Scope

Semantic Core v0.3 has production execution paths for semantic generation, semantic invariant discovery/verification, normalized usage telemetry and provider-boundary budgets, eligible prompt suboptimization, persisted semantic evidence, hardened explicit-route context selection, baseline-aware Pareto selection, and feedback-directed repair.

The milestone does not claim perfect agent simulation, autonomous application of generated patches, strict pre-reservation of unknown provider token/USD cost, or universal model-provider support. Those are outside the v0.3 scope rather than hidden guarantees.
