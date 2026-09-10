# AI Documentation Optimizer — Semantic Core Remaining Work Specification v0.3

Status: implementation specification — remaining work only

## 1. Purpose

This document contains only the work that still blocks completion of the Semantic Core v0.3 milestone.

Implemented behavior belongs in human and agent documentation, not in this specification:

- [`docs/guides/semantic-optimization.md`](../docs/guides/semantic-optimization.md) — human-facing behavior and operating model;
- [`docs/design/architecture.md`](../docs/design/architecture.md) — implementation boundaries and causal flow;
- [`.ai/skills/semantic-optimization-review/SKILL.md`](../.ai/skills/semantic-optimization-review/SKILL.md) — agent review procedure.

The milestone is not complete merely because CI is green. A capability counts only when the normal product path wires it, it causally affects behavior, and the acceptance coverage can detect a plausible regression.

## 2. Remaining Work A — make all active budgets truthful at the provider boundary

### Problem

The production CLI now wires `CommandSemanticProvider` through `BudgetedSemanticProvider`, and request usage is bounded before another provider invocation is started. However the CLI currently passes only `max_llm_requests` into that provider wrapper.

`max_input_tokens`, `max_output_tokens`, and `max_cost_usd` remain active configuration controls but are enforced only after accumulated candidate/run usage is observed. A single candidate cycle can therefore perform generation, prompt suboptimization, invariant verification, and scenario evaluation that crosses one of those limits before the next search-level check.

### Required behavior

The normal CLI semantic stack MUST pass every active provider budget into the production budget wrapper:

- maximum external requests;
- maximum input tokens;
- maximum output tokens;
- maximum USD cost.

Known accumulated usage MUST prevent a later provider invocation after a configured limit has been reached.

If a provider can provide a trustworthy next-call estimate, the adapter SHOULD reject a call that is expected to exceed the remaining token or USD budget. If no trustworthy pre-call estimate exists, post-call provider-reported usage may cross the boundary once, but the run MUST report that overrun truthfully and MUST perform no further external work.

Do not claim a strict pre-call token/USD guarantee when only post-call usage is available.

Deterministic/offline operation MUST continue to consume zero external request/token/USD budget.

### Acceptance tests

- CLI/runtime wiring passes request, input-token, output-token, and USD limits to the production budget wrapper;
- provider-reported generation/evaluation/suboptimizer usage remains separately aggregated;
- reaching the request limit prevents another external call;
- reaching the input-token limit prevents another external call;
- reaching the output-token limit prevents another external call;
- reaching the USD limit prevents another external call;
- a provider-reported one-call overrun is persisted truthfully and stops all subsequent external work;
- deterministic operation consumes zero external usage.

## 3. Remaining Work B — make critical invariant verification contradiction-safe

### Problem

Semantic invariant discovery and verification are now wired into the production search path. High-confidence semantic discoveries can protect critical behavior that lacks MUST/NEVER-style keywords.

The remaining safety flaw is verification short-circuiting: if the original invariant sentence is still present literally, the current verifier records it as preserved without asking the semantic layer whether another part of the candidate contradicts or weakens it.

For example, this must not pass merely because the first sentence survived:

```md
MUST run validation before merge.

For migration-only changes, validation is optional and may be skipped.
```

### Required behavior

Deterministic literal preservation remains useful cheap evidence, but it MUST NOT be treated as sufficient proof that a critical invariant is globally preserved when production semantic verification is available.

The critical-invariant decision model MUST distinguish at least:

- preserved exactly;
- preserved semantically with different wording;
- weakened;
- removed;
- uncertain/contradicted.

A contradiction elsewhere in the effective candidate documentation MUST produce weakened/uncertain/rejected behavior rather than a literal-preserved success.

Weakened, removed, contradicted, and uncertain critical behavior MUST reject the candidate unless a future explicit repository-owned policy says otherwise.

### Acceptance tests

- exact critical wording plus a contradictory exception elsewhere is rejected or marked uncertain;
- meaning-preserving paraphrase passes;
- MUST → SHOULD/recommended weakening fails;
- removal fails;
- a critical baseline instruction without normative magic keywords is discovered and protected.

## 4. Remaining Work C — make semantic invariant discovery explainable and conservative

### Problem

Production semantic discovery currently filters provider results to high-confidence critical invariants. This is a useful guard against promoting every sentence, but `critical + confidence >= threshold` is not enough evidence for post-run explanation and does not itself prove a low false-positive rate.

### Required behavior

Semantic invariant discoveries MUST preserve explainable provenance sufficient to answer why a statement became a critical invariant. Prefer extending the existing `Invariant`/evidence model rather than adding a parallel artifact system.

At minimum, a semantic critical invariant SHOULD retain:

- source path/section;
- source statement or evidence fragment;
- provider/domain rationale for criticality;
- confidence;
- discovery source (`literal` or `semantic`).

The core MUST remain conservative: ordinary descriptive text must not become a critical invariant only because it is semantically related to the task domain.

### Acceptance tests

- a semantic critical invariant persists rationale/provenance that can be inspected after the run;
- an ordinary descriptive sentence is not promoted to a critical invariant;
- duplicate literal/semantic discoveries do not create duplicate hard constraints.

## 5. Remaining Work D — close production-wiring acceptance gaps

### Problem

The production semantic adapter classes are exercised together in integration tests, but the strongest test currently constructs those classes and injects them directly into `SearchController`. This proves adapter interoperability but does not prove the actual CLI stack configuration.

The semantic generator request also contains feedback and search memory, but current fake-provider coverage mainly proves their presence rather than demonstrating that changed contents are observable by the production adapter.

### Required behavior

Add a focused CLI/runtime acceptance test that exercises the same path an operator uses:

```text
AI_DOC_SEMANTIC_COMMAND
  -> CLI semantic stack construction
  -> budget wrapper
  -> semantic generation/invariant service/evaluation/GEPA as enabled
  -> SearchController
```

CI may continue to use the deterministic command fixture and MUST NOT make paid network calls.

Changing meaningful feedback or search-memory contents MUST change the provider request payload and/or the resulting semantic generation in a testable way. Merely serializing an always-present object is insufficient evidence.

### Acceptance tests

- normal CLI/runtime selects the production semantic stack from `AI_DOC_SEMANTIC_COMMAND`;
- the production adapter, not an injected fake domain implementation, receives the request;
- changed feedback contents are visible to or affect semantic generation;
- changed search-memory contents are visible to or affect semantic generation;
- external request accounting from that CLI path matches provider usage.

## 6. Remaining Work E — prove GEPA regressions are rejected

### Problem

Enabled GEPA with an eligible `<!-- ai-doc:gepa -->` artifact now invokes the production prompt-suboptimizer and its output enters the normal candidate pipeline. Usage is accounted separately and ineligible/no-provider behavior remains a truthful no-op.

The remaining gap is acceptance coverage: there is no focused regression proving a harmful GEPA rewrite is rejected by the same invariant/evaluation gates as another candidate mutation.

### Required behavior

Add an end-to-end regression test where the production prompt-suboptimizer changes an eligible artifact in a way that violates required behavior and the candidate is rejected by the normal safety/evaluation path.

Do not add a GEPA-specific bypass or safety mechanism. The purpose of the test is to prove that the existing common gates are causal.

### Acceptance tests

- enabled + eligible invokes prompt suboptimization;
- a safe GEPA rewrite can proceed through normal evaluation;
- a GEPA-produced critical or behavioral regression is rejected;
- GEPA request/token/USD usage remains separately inspectable;
- enabled + ineligible remains an explicit truthful no-op.

## 7. Remaining Work F — strengthen recommendation/evidence explanation

### Problem

Run artifacts now persist repair feedback, invariant decisions, effective context, normalized usage, candidate status/rejection reasons, lineage, frontier state, and run-level recommendation/no-change reasoning.

The current recommendation reason is still coarse (for example, `non-dominated and policy-qualified`). A reviewer can reconstruct the decision from `run.json`, but the artifact does not directly explain which objective improvements and policy thresholds justified replacement of the baseline.

### Required behavior

Recommendation/no-change evidence SHOULD be explicit enough to answer without recomputing the policy:

- which candidate, if any, beat the baseline recommendation policy;
- which objective(s) materially improved;
- which allowed regressions/tolerances were used;
- why baseline/no-change won when no candidate qualified.

Prefer extending the existing run/candidate evidence models. Do not create a second reporting subsystem.

### Acceptance tests

- recommended candidate persists concrete recommendation factors rather than only a generic label;
- baseline/no-change persists the concrete blocking factors for the best attempted candidates;
- persisted recommendation evidence agrees with objective vectors and configured policy.

This work is lower risk than Sections 2–4 but remains part of the v0.3 explainability goal.

## 8. Tier-0 provider-call semantics — clarification

The previous wording "Tier-0 rejection proves no semantic/provider call was made" is too broad now that semantic invariant verification itself is part of the safety gate.

The intended contract is:

- deterministic static/literal failures SHOULD prevent unnecessary downstream semantic evaluation and generation-dependent work;
- semantic invariant calls ARE allowed when they are necessary to determine whether a critical invariant is preserved;
- once a candidate is rejected by an already-known hard constraint, no additional semantic evaluation or suboptimization should run for that candidate.

Acceptance tests SHOULD assert call types/counts rather than the impossible blanket rule that every Tier-0 rejection performs zero provider calls.

## 9. Definition of Done

Semantic Core v0.3 is complete when all of the following are true:

- all active request/token/USD limits are wired and enforced truthfully at the production provider boundary, with any unavoidable one-call post-report overrun explicitly represented;
- critical invariant verification cannot be bypassed by retaining literal wording while adding a contradiction elsewhere;
- semantic invariant discovery persists explainable provenance and has regression coverage against ordinary-sentence overclassification;
- the real CLI semantic-stack wiring is covered with the deterministic production command adapter;
- feedback and search-memory contents demonstrably reach/affect production semantic generation;
- a GEPA-produced regression is demonstrably rejected by the common safety/evaluation path;
- recommendation/no-change evidence is sufficiently concrete for post-run explanation without recomputing policy decisions;
- cross-platform CI remains green;
- normal CI makes no paid network calls.

## 10. Engineering constraints

Do not reopen already completed semantic-loop, Pareto, packaging, context-routing, baseline-selection, or artifact-system work without evidence of a defect.

Do not add new provider SDK coupling to optimizer domain models. Keep the provider-neutral command boundary and deterministic offline path.

Prefer a small number of adversarial acceptance tests over new abstractions. The remaining work is primarily truthfulness and safety hardening, not architecture expansion.
