# AI Documentation Optimizer — Semantic Core Remaining Work Specification v0.3

Status: implementation specification — remaining work only

## 1. Purpose

The first implementation pass made the central semantic search loop causally real. This document no longer repeats requirements that are already implemented and covered by tests. It defines only the work still required before the semantic-core milestone can be called complete.

Human-facing documentation for the implemented behavior lives in [`docs/guides/semantic-optimization.md`](../docs/guides/semantic-optimization.md). Architecture-level context lives in [`docs/design/architecture.md`](../docs/design/architecture.md).

The product goal remains:

> Given AI-facing repository documentation, produce candidate documentation changes that reduce context cost and/or improve clarity while preserving required behavior, evaluate those candidates against the baseline, reject unsafe regressions, and recommend a non-dominated candidate only when evidence supports the recommendation.

## 2. Already implemented — preserve, do not rebuild

The following capabilities are accepted as implemented for this milestone and MUST NOT be redesigned merely to make this specification look more complete:

- `SearchController` consumes `EvaluationSuite` and evaluation evidence affects candidate status and objectives;
- deterministic Tier-0 gates run before semantic evaluation;
- DeepEval evaluates baseline content when no candidate is supplied;
- Promptfoo assertions are isolated per scenario and the lexical adapter does not claim semantic evaluation;
- evaluation-derived feedback can drive a child repair and the child is re-evaluated;
- an end-to-end fake-semantic integration test exercises fail → feedback → repair → re-evaluate → recommend;
- baseline participates in Pareto comparison and the recommendation policy may return no change;
- effective task context is distinguished from the full documentation corpus through a context-selection boundary;
- deterministic candidate operations do not consume LLM-request budget;
- GEPA currently reports truthfully when no eligible prompt artifact is wired instead of pretending optimization occurred;
- run, frontier, lineage, search-memory, report, candidate proposal/diff/evaluation artifacts already exist.

These are documented for humans rather than repeated below as unfinished implementation tasks.

## 3. Guiding rule

A capability counts as complete only when it exists in a production execution path and causally affects behavior. A Protocol, injected fake, config field, metadata field, or unit test proving an extension seam is not by itself a product capability.

Prefer completing an existing path over introducing another abstraction.

## 4. Remaining Work A — production semantic candidate generation

### Problem

The optimizer has a semantic-generation boundary, and tests prove a semantic generator can receive strategy, previous summaries, explored transformations, feedback, and search memory. The normal CLI path does not currently wire a production semantic generator. Adaptive modes therefore still rely on deterministic/regex mutation providers unless a generator is injected programmatically.

### Required behavior

At least one production semantic candidate-generation implementation MUST be wired into an adaptive mode (`balanced` and/or `search`). It MUST be able to change candidate content based on semantic reasoning rather than only predefined regex transformations.

The generator MUST receive and meaningfully use, when available:

- current/baseline documentation;
- extracted invariants;
- strategy/objective weaknesses;
- previous candidate summaries;
- explored transformations/fingerprints;
- structured parent feedback;
- search memory.

Provider-specific SDK objects MUST remain outside optimizer domain models. The generator returns the existing proposal/rendered-document representation.

Deterministic generators MUST remain usable for conservative/offline/no-model operation.

### Acceptance tests

- a production-wiring test proves the CLI/runtime can select a semantic generator rather than only an injected unit-test fake;
- a deterministic fake provider may stand in for the network/model in CI, but it MUST exercise the same production adapter and wiring;
- changing feedback/search memory changes the request or resulting semantic generation behavior in a testable way;
- request accounting records the external generation request.

## 5. Remaining Work B — semantic invariant discovery and verification

### Problem

Literal invariant extraction is a useful Tier-0 guard. A semantic verifier boundary also exists, and tests prove it can accept a meaning-preserving rewrite or reject a weakened invariant. The normal production path does not wire a concrete semantic verifier. In addition, semantic verification can only protect invariants that were first discovered by the current mostly keyword-oriented extraction logic.

### Required behavior

Critical behavior MUST have two complementary safety layers:

1. deterministic extraction/verification for obvious normative language such as MUST, NEVER, REQUIRED, and FORBIDDEN;
2. semantic discovery/verification capable of protecting critical behavior even when the baseline does not use those exact keywords.

The production semantic layer MUST distinguish at least:

- preserved exactly;
- preserved semantically with different wording;
- weakened;
- removed;
- uncertain.

For critical behavior, weakened, removed, and uncertain MUST reject the candidate unless an explicit repository-owned policy says otherwise.

The implementation MUST avoid converting every ordinary sentence into a critical invariant. Semantic discovery therefore needs evidence/severity rules and explainable output.

### Acceptance tests

- a production-wiring test exercises the concrete semantic verifier through the normal search path;
- a meaning-preserving paraphrase passes;
- MUST → SHOULD/recommended weakening fails;
- removal fails;
- contradiction elsewhere in the candidate fails or becomes uncertain/rejected;
- a critical baseline instruction without magic normative keywords is discovered and protected;
- an ordinary descriptive sentence is not falsely promoted to a critical invariant.

## 6. Remaining Work C — real token and USD telemetry

### Problem

Request counters now distinguish deterministic work from external generation/evaluation/suboptimizer calls. Token and USD fields exist, but they are not yet consistently populated from actual provider work. Consequently request budgets are meaningful while token/cost budgets are not yet fully evidence-backed.

### Required behavior

External adapters MUST return normalized usage telemetry where the provider exposes it, or a documented estimate where exact usage is unavailable.

Track separately where possible:

- generation requests;
- semantic evaluation requests;
- prompt-suboptimizer requests;
- input tokens;
- output tokens;
- provider-reported or estimated USD cost;
- deterministic operations;
- cache hits, if a provider exposes them.

`max_llm_requests` MUST continue to bound actual external requests.

`max_input_tokens` and `max_output_tokens` MUST either be enforced against real/estimated external usage or be removed from the active configuration contract until they can be truthful.

`max_cost_usd` MUST stop additional paid work once known/estimated cost reaches the configured limit. When a next-call estimate is available, the budget SHOULD be checked before the call.

A zero-cost deterministic run MUST remain possible.

### Acceptance tests

- deterministic transformations consume zero external requests/tokens/USD;
- fake production providers return usage and it is aggregated into candidate/run telemetry;
- generation and evaluation usage remain distinguishable;
- request budget stops further external work;
- cost budget stops further external work;
- token budgets are either demonstrably enforced or no longer advertised as active controls;
- reports identify estimated versus provider-reported cost where that distinction exists.

## 7. Remaining Work D — behaviorally effective GEPA integration

### Problem

GEPA configuration is currently truthful: when no eligible prompt artifact is wired, the run reports that nothing was optimized and why. This satisfies truthfulness but not behavioral integration.

### Required behavior

When GEPA is enabled and an eligible prompt artifact exists, the production path MUST invoke the prompt suboptimizer and use its output in the optimization workflow.

GEPA remains a suboptimizer, not the outer documentation search controller. Its output MUST pass through the same applicable invariant, evaluation, budget, and Pareto/recommendation gates as other changes.

When no eligible artifact exists, the existing explicit no-op explanation remains valid and MUST be preserved.

### Acceptance tests

- enabled + eligible invokes the production prompt-suboptimizer boundary;
- the optimized artifact causally affects a candidate/evaluation path;
- suboptimizer requests/tokens/cost are accounted separately;
- enabled + ineligible remains an explicit truthful no-op;
- a GEPA-produced regression can still be rejected by normal safety/evaluation gates.

## 8. Remaining Work E — evidence and explainability artifacts

### Problem

Current artifacts preserve candidate files, proposal, diff, evaluation, run state, frontier, lineage, search memory, and report. They do not yet preserve enough structured evidence to reconstruct every important semantic decision after the run.

### Required behavior

Persist enough structured evidence to answer, without rerunning the optimizer:

- why was this candidate generated and from which parent(s)?
- which feedback was used to create a repair child?
- which scenarios passed or failed and with what evidence?
- which deterministic and semantic invariants were checked, and what was each result?
- which documents formed the effective context for each scenario?
- what static/context-cost metrics changed relative to baseline/parent?
- what external requests, tokens, and USD cost were consumed?
- why was the candidate rejected, retained on the frontier, or recommended?
- why did baseline/no-change win when no candidate was recommended?

Prefer extending existing JSON artifacts/models rather than inventing a parallel artifact system.

### Acceptance tests

- the repair integration scenario persists the feedback used by the child;
- semantic invariant decisions are inspectable after the run;
- effective-context evidence is persisted per scenario;
- recommendation/no-recommendation has an inspectable reason;
- telemetry in artifacts matches the run counters.

## 9. Remaining Work F — strengthen context-selection adversarial safety

### Problem

The current deterministic context selector correctly distinguishes always-loaded/root instructions from task-selected reference documents. It is intentionally approximate. Keyword overlap can still overestimate whether a weak router would cause a real agent to discover a referenced document.

### Required behavior

Do not replace the context-selection boundary. Harden it so the optimizer cannot cheaply game evaluation by preserving task keywords while weakening actual routing/discoverability.

The model SHOULD distinguish, where practical:

- a document merely mentioning task vocabulary;
- an explicit route/link/trigger telling the agent when to load another document;
- whether the selected document is reachable from always-loaded context;
- ordering of selected context;
- a route that is present but too weak/ambiguous to satisfy required behavior.

Perfect simulation of Claude, Codex, Copilot, or every coding agent remains a non-goal.

### Acceptance tests

- extraction reduces always-loaded tokens while the relevant detail remains reachable;
- weakening the router cannot pass merely because root and target documents share keywords;
- unrelated references are not selected;
- the parent-fail/child-repair scenario asserts that the child preserves the parent's context saving as well as restoring behavior.

## 10. Remaining Work G — close explicit acceptance-test gaps

Add the following focused regression tests even where the underlying code already appears capable:

1. baseline legitimately remains best and produces no recommended change after semantic candidates were evaluated;
2. the router-repair child preserves the parent's useful context-cost improvement;
3. extracted documentation remains reachable after repair;
4. semantic reliability remains unavailable rather than fabricated when no semantic evaluator ran;
5. Tier-0 rejection proves no semantic/provider call was made;
6. production semantic generation/verifier adapters are exercised with deterministic fake providers, not only injected fake domain implementations.

Normal CI MUST NOT require paid network calls.

## 11. Implementation order

Implement remaining work in this order unless a concrete dependency justifies changing it:

### Phase 1 — semantic production path

- wire production semantic candidate generation;
- wire semantic invariant discovery/verification;
- add production-adapter tests with deterministic fake providers.

### Phase 2 — FinOps truthfulness

- normalize provider usage telemetry;
- aggregate request/token/USD usage;
- enforce request/cost/token contracts truthfully.

### Phase 3 — evidence

- persist feedback used for repair;
- persist invariant decisions and recommendation reasoning;
- make telemetry/effective-context evidence easy to inspect.

### Phase 4 — GEPA

- connect eligible prompt artifacts to the existing suboptimizer boundary;
- account for GEPA work;
- route its result through normal safety/evaluation gates.

### Phase 5 — adversarial context hardening

- strengthen router/discoverability simulation;
- add anti-gaming tests;
- run the planned independent adversarial review against the completed semantic path.

## 12. Non-goals

This remaining-work milestone does not require:

- replacing the existing Pareto algorithm;
- replacing deterministic analyzers/generators;
- redesigning packaging or the `.tools` consumption model;
- broad new CLI surface;
- a generic autonomous coding agent;
- a hosted SaaS control plane;
- vector databases/RAG infrastructure;
- fine-tuning;
- support for every LLM provider;
- perfect simulation of every coding agent;
- 100% semantic automation with no deterministic safety layer.

## 13. Definition of Done

The semantic-core milestone is complete when all of the following remaining conditions are true:

- a production semantic generation path can affect candidate content in adaptive mode;
- semantic invariant discovery/verification is wired into the production search path and protects critical behavior beyond magic keywords;
- request/token/USD telemetry represents real or explicitly estimated external work;
- configured cost/request/token limits are truthful and enforced, or unsupported limits are removed from the active contract;
- GEPA performs real suboptimization when enabled and eligible, while retaining truthful no-op behavior when ineligible;
- artifacts persist feedback, semantic invariant decisions, effective context, telemetry, and recommendation/no-change reasoning sufficiently for post-run explanation;
- context-selection tests prevent trivial keyword-based routing games and prove useful context savings survive repair;
- the explicit regression tests in section 10 pass;
- cross-platform CI remains green;
- normal CI uses fake providers and makes no paid network calls.

## 14. Final engineering constraint

Do not reopen already completed semantic-loop work without evidence of a defect.

The remaining problem is not to make the architecture larger. It is to turn the remaining extension seams and telemetry fields into truthful production behavior, preserve evidence, and make the optimizer harder to game.