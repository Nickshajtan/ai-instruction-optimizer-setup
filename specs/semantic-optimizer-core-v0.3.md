# AI Documentation Optimizer — Semantic Core Implementation Specification v0.3

Status: implementation specification

## 1. Purpose

The repository already has a strong portable tool shell, static analyzers, candidate/search domain models, Pareto selection, feedback primitives, evaluator adapters, extension boundaries, packaging, and cross-platform CI.

The next milestone MUST NOT expand architecture merely to match older specifications. It MUST make the existing optimization architecture causally real end-to-end.

The product goal is:

> Given AI-facing repository documentation, produce candidate documentation changes that reduce context cost and/or improve clarity while preserving required behavior, evaluate those candidates against the baseline, reject unsafe regressions, and recommend a non-dominated candidate only when evidence supports the recommendation.

This specification therefore prioritizes the semantic optimization loop over additional packaging, adapters, CLI surface area, or abstractions.

## 2. Guiding rule

Existing specifications describe intent, not law.

Before changing an existing subsystem, preserve an implementation that already satisfies the intent in a cleaner or more extensible way. Do not rewrite working Pareto, packaging, plugin, public API, or cross-platform infrastructure merely because its shape differs from an earlier document.

A subsystem counts as implemented only when its output causally affects the product workflow. Having a class, config flag, adapter, model, test fixture, or metadata field is not sufficient.

## 3. Current strengths to preserve

Do not regress these areas unless a change is required by the semantic loop:

- portable CLI and source-checkout usage;
- `.tools` / black-box consumption model;
- wheel and executable packaging paths;
- `ai_doc.api.v1` public boundary;
- extension/plugin boundary;
- Linux, Windows, and macOS CI;
- static analyzers and deterministic context-cost analysis;
- separated optimizer modules rather than a giant optimizer class;
- Pareto dominance/frontier implementation, including tolerances and objective directions;
- deterministic candidate transformations as cheap mutation primitives;
- optional DeepEval / Promptfoo isolation from core dependencies.

## 4. Primary acceptance scenario

The milestone is complete only when one real vertical slice works:

1. Load baseline documentation and repository-owned evaluation scenarios.
2. Extract safety invariants from the baseline.
3. Generate at least one meaningful candidate mutation.
4. Run deterministic Tier-0 gates.
5. Run a real per-scenario semantic/behavioral evaluation for candidates that pass Tier 0.
6. Build an objective vector from actual evaluation evidence and static/context-cost metrics.
7. Insert valid candidates into Pareto selection.
8. Produce structured feedback from a failed or weak candidate evaluation.
9. Generate at least one child candidate using that feedback while preserving useful parent changes.
10. Re-evaluate the child through the same gates.
11. Recommend a candidate only if hard constraints pass and the candidate is justified relative to baseline/frontier.
12. Persist enough evidence to explain why the candidate was generated, rejected, repaired, or recommended.

An integration test MUST demonstrate this complete causal chain. Manually constructing the feedback object inside that acceptance test does not satisfy step 8.

## 5. Evaluation architecture

### 5.1 Tier 0 — deterministic gate

Tier 0 remains cheap and MUST run before paid semantic evaluation.

It SHOULD include existing static analyzers, document parsing/graph validation, context-cost calculation, deterministic invariant checks, candidate fingerprint/deduplication, and detection of newly introduced static errors.

A Tier-0 hard failure MUST prevent unnecessary semantic/model calls.

Existing deterministic checks are safety/performance primitives; do not remove them merely because semantic evaluation is added.

### 5.2 Tier 1 — behavioral semantic evaluation

`SearchController` MUST actually consume the `EvaluationSuite`. The suite MUST NOT be discarded or treated as metadata.

Each scenario MUST be evaluated independently. Required and forbidden behavior from scenario A MUST NOT leak into scenario B.

The evaluator result MUST feed candidate hard constraints and/or the objective vector. `reliability` MUST NOT silently represent only deterministic invariant recall when semantic evaluation is configured and required.

Evaluation MUST compare behavior supported by candidate documentation with the intended scenario behavior. A lexical `contains` check may exist as a cheap evaluator, but MUST NOT be presented as deep semantic evaluation.

### 5.3 Tier 2 — expensive/adaptive evaluation

Expensive evaluators, including GEPA-related prompt optimization where applicable, MAY be invoked only for candidates that survive cheaper gates and where the configured mode/budget permits it.

Tier 2 is not required for every candidate.

## 6. Fix evaluator correctness before integration

### 6.1 DeepEval baseline bug

When `candidate is None`, DeepEval MUST evaluate the baseline documentation rather than an empty document set.

Add a regression test proving that `check --deep` supplies baseline documentation to the evaluator.

### 6.2 Promptfoo scenario isolation

Promptfoo assertions MUST be built per scenario. A scenario's `expected_required` / forbidden expectations MUST apply only to that scenario.

Add a test with at least two scenarios whose requirements differ and prove there is no cross-scenario assertion leakage.

### 6.3 Promptfoo semantic naming

If the current `echo + contains` adapter is retained, classify it as deterministic/lexical evaluation. Deep/semantic mode MUST use a provider/judge capable of evaluating behavior, or the CLI/report MUST clearly state that semantic evaluation was not performed.

Never claim semantic reliability from an echo/contains result alone.

## 7. Candidate generation

Existing regex/deterministic generators MUST be preserved as cheap mutation providers, but they MUST NOT be the only effective optimization mechanism in modes that promise adaptive or semantic optimization.

Introduce or wire a semantic candidate-generation boundary that can propose repository documentation changes from:

- baseline/current candidate documentation;
- extracted invariants;
- current objective weaknesses;
- previous candidate summaries;
- explored transformation memory;
- structured parent feedback;
- configured optimization strategy.

The existing `previous_summaries`, `explored_transformations`, and `SearchMemory` inputs MUST either affect generation or be removed from the active contract. Do not keep fake inputs that are immediately discarded.

Semantic generation MUST return the same domain-level proposal/rendered-document representation used by the search pipeline. Provider-specific response objects MUST NOT leak into optimizer domain models.

Deterministic generators SHOULD remain available for conservative/offline/no-model operation.

## 8. Feedback-directed repair

Feedback MUST be derived from actual candidate evaluation evidence rather than only hand-authored fixtures.

`FeedbackBuilder` SHOULD produce structured data containing, where available:

- failed scenario IDs;
- violated or weakened required behavior;
- forbidden behavior triggered;
- invariant regressions;
- clarity/static regressions;
- context-cost changes;
- suspected cause;
- suggested mutation directions;
- successful parent transformations worth preserving.

A child mutation MUST be able to use this feedback.

Required integration scenario:

- parent candidate achieves a useful context-cost improvement;
- parent fails one behavioral scenario because a router/instruction became too weak;
- feedback identifies the weakness;
- child preserves the extraction/context saving;
- child strengthens the relevant routing/instruction behavior;
- child passes the previously failing scenario.

The existing deterministic router-strengthening repair may be used as one repair strategy, but the feedback itself MUST come from the evaluation pipeline in the acceptance scenario.

## 9. Invariant safety

Current literal critical-invariant verification remains a useful Tier-0 guard but is insufficient as the complete safety model.

Implement two layers:

1. deterministic extraction/verification for obvious normative language such as MUST, NEVER, REQUIRED, FORBIDDEN;
2. semantic verification for meaning-preserving rewrites and critical behavior that does not contain those exact keywords.

The system MUST distinguish at least these cases:

- exact invariant preserved;
- semantically equivalent invariant preserved with different wording;
- invariant weakened;
- invariant removed;
- uncertain.

For critical invariants, weakened, removed, or uncertain results MUST reject the candidate unless configuration explicitly defines a stricter repository-owned policy.

Do not weaken the cheap literal gate; add semantic coverage around it.

## 10. Objective vectors and Pareto

Preserve the existing Pareto implementation unless a failing test demonstrates a mathematical defect.

Fix the evidence feeding it.

At minimum, candidate objectives SHOULD represent:

- behavioral reliability from actual evaluation;
- clarity/static quality;
- critical invariant preservation;
- always-loaded tokens;
- expected context tokens;
- estimated context cost.

A metric MUST NOT appear precise when it is not backed by evidence. If semantic reliability was not evaluated, represent it as unavailable or explicitly degraded rather than silently substituting an unrelated heuristic.

Baseline MUST participate in comparison so the optimizer can conclude that no candidate is safely better.

The optimizer MUST be allowed to recommend no change.

## 11. Agent-context / routing semantics

This is a domain requirement beyond simple Markdown concatenation.

The optimizer exists partly to move low-frequency detail out of always-loaded context and replace it with discoverable routing. Therefore semantic evaluation MUST NOT assume that every repository document is always concatenated into model context.

Introduce an explicit context-selection simulation boundary.

Given a task/scenario and repository documentation, it SHOULD model or approximate:

1. always-loaded/root instructions;
2. router/trigger decisions;
3. referenced/on-demand documents selected for the task;
4. ordering of selected context;
5. resulting effective context and token cost.

Behavioral evaluation SHOULD judge the effective selected context, not an unconditional concatenation of every Markdown document.

The first implementation may be deterministic and intentionally simple, but it MUST expose the distinction between:

- repository documentation corpus;
- always-loaded context;
- task-selected context.

Add tests proving that extracting a large section can reduce always-loaded tokens without making task-required detail unreachable.

## 12. GEPA integration

The existing DeepEval GEPA adapter may be preserved.

When `--gepa` or equivalent runtime configuration is enabled, the flag MUST cause an actual eligible prompt-level optimization step or the command MUST explicitly report that no eligible artifact was optimized and why.

Do not accept a state where GEPA configuration is only copied into run metadata.

GEPA remains a sub-optimizer, not the outer documentation search controller. Its output MUST pass through the same invariant, evaluation, budget, and Pareto gates as other mutations.

## 13. Budget and telemetry correctness

Budget accounting MUST reflect real external work.

Do not increment `generation_requests` or `evaluation_requests` for deterministic local operations as though they were LLM calls.

Track separately where possible:

- deterministic candidate operations;
- generation model requests;
- semantic evaluation requests;
- prompt-suboptimizer requests;
- input/output tokens;
- estimated or provider-reported USD cost;
- cache hits if available.

`max_llm_requests` MUST bound actual model requests.

`max_cost_usd` MUST stop additional paid work once the known/estimated budget is exhausted.

A zero-cost deterministic run MUST remain possible.

Budget checks SHOULD occur before starting the next external request whenever its estimated cost can be known.

## 14. Reporting and evidence

Persist sufficient run artifacts to answer:

- What changed in candidate Cxxx?
- Why was it generated?
- Which parent(s) did it come from?
- Which scenarios passed/failed?
- Which invariants were preserved or regressed?
- What effective context was evaluated?
- What were the static/context-cost metrics?
- What external requests/cost were consumed?
- Why was it rejected or retained?
- Why is the recommended candidate preferable to baseline?

Existing `run.json`, `frontier.json`, `lineage.json`, `search-memory.json`, and `report.json` SHOULD be extended rather than replaced where practical.

## 15. CLI behavior

Do not add broad new CLI surface unless required.

Existing `check`, `optimize`, `--deep`, strategy, budget, frontier, GEPA, JSON, and debug options SHOULD become truthful before new options are introduced.

`--non-interactive` MUST NOT be silently discarded if an operation may trigger external calls. In non-interactive mode, behavior must be deterministic from config/flags and suitable for CI.

Commands that may make paid/external calls SHOULD make that fact visible in console output/report metadata.

## 16. Testing requirements

Add or update tests covering at least:

1. DeepEval uses baseline when candidate is absent.
2. Promptfoo requirements are isolated per scenario.
3. Search consumes `EvaluationSuite` and evaluator results affect candidate status/objectives.
4. A failed semantic evaluation rejects a candidate when configured as required.
5. Semantic reliability is not fabricated when no semantic evaluation ran.
6. Feedback is built from evaluation failure and used by a child mutation.
7. The vertical repair scenario described in section 8 passes end-to-end.
8. Meaning-preserving critical invariant rewrite is not falsely rejected by semantic verification.
9. A weakened/removed critical invariant is rejected.
10. Task-context selection distinguishes always-loaded and on-demand documentation.
11. Extracted documentation remains reachable for a relevant task.
12. Real external requests consume request budget; deterministic transforms do not.
13. Cost budget can stop further external candidate/evaluation work.
14. `--gepa` either performs a real eligible suboptimization or truthfully reports why it did not.
15. Baseline may remain the best outcome and produce no recommended change.

Use fakes/stubs for provider calls in normal CI. Tests MUST NOT require paid network calls.

At least one integration test MUST exercise the complete search/evaluate/feedback/repair/re-evaluate/recommend pipeline with deterministic fake semantic providers.

## 17. Implementation order

Implement in this order unless repository constraints justify a different sequence:

### Phase A — correctness bugs

- fix DeepEval baseline handling;
- fix Promptfoo per-scenario assertion isolation;
- make evaluator classification/reporting truthful.

### Phase B — semantic evaluation in search

- define/wire evaluator boundary into `SearchController`;
- consume `EvaluationSuite`;
- propagate evaluation results into hard constraints/objectives/reporting;
- keep Tier-0 gate before semantic calls.

### Phase C — real feedback loop

- build feedback from evaluation evidence;
- feed it into child generation;
- implement the end-to-end router repair integration scenario.

### Phase D — semantic generation and invariants

- activate meaningful search-memory/feedback inputs;
- add semantic candidate generator provider boundary;
- add semantic critical-invariant verification.

### Phase E — context routing semantics

- introduce effective-context selection/simulation;
- evaluate task-selected context rather than unconditional corpus concatenation;
- measure always-loaded vs selected context.

### Phase F — GEPA and FinOps truthfulness

- integrate GEPA into eligible search steps;
- wire real request/token/cost accounting;
- enforce actual request and cost budgets.

Do not begin another packaging/framework redesign before Phases A-C are complete.

## 18. Non-goals

This milestone does not require:

- replacing the existing Pareto algorithm;
- replacing deterministic analyzers/generators;
- a generic autonomous coding agent;
- a hosted SaaS control plane;
- vector databases or RAG infrastructure;
- fine-tuning;
- mandatory DeepEval or Promptfoo core dependencies;
- production-grade provider support for every LLM vendor;
- perfect simulation of every AI coding tool's context-loading behavior;
- new packaging architecture;
- rewriting working public APIs only for aesthetic consistency.

## 19. Definition of Done

The milestone is done when all of the following are true:

- `ai-doc optimize` no longer discards the evaluation suite;
- candidate semantic evaluation causally affects status/objectives/frontier/recommendation;
- deterministic gates run before expensive evaluation;
- DeepEval baseline behavior is correct;
- Promptfoo scenarios do not leak assertions across cases;
- deep/semantic claims correspond to real semantic evaluation;
- at least one non-deterministic/semantic generation path can affect candidate content in adaptive modes;
- evaluation-derived feedback can produce and repair a child candidate;
- critical invariants have deterministic plus semantic safety coverage;
- effective task context is distinguished from the full documentation corpus;
- Pareto compares evidence-backed objectives and baseline may legitimately win;
- GEPA configuration is behaviorally effective when enabled and eligible;
- request/cost budgets correspond to actual external work;
- run artifacts explain candidate lineage, evaluation evidence, context selection, and rejection/recommendation reasons;
- cross-platform CI remains green;
- normal tests use fake providers and require no paid network calls;
- one end-to-end integration test demonstrates: generate → gate → semantic evaluate → fail → feedback → repair → re-evaluate → Pareto/recommend.

## 20. Final engineering constraint

Prefer completing one real causal path over adding five new abstractions.

If an implementation choice makes the architecture look more sophisticated but does not improve the optimizer's ability to generate, evaluate, repair, or safely recommend documentation changes, defer it.