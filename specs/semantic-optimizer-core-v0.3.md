# AI Documentation Optimizer — Semantic Core v0.3

Status: implementation substantially complete; known acceptance gaps remain

## 1. Purpose

This document is the live acceptance and remaining-work specification for Semantic Core v0.3.

It reconciles:

- the v0.3 remaining-work contract on `main` before this branch;
- the implementation currently present on `feat/semantic-core-v0.3-completion`;
- the latest critical acceptance review of that implementation.

The branch has completed most of the original v0.3 work. It MUST NOT, however, declare the milestone complete merely because the production seams exist or CI is green. The known gaps in this document remain part of v0.3 until they are fixed and covered by behavioral tests.

The product goal remains:

> Given AI-facing repository documentation, produce candidate documentation changes that reduce context cost and/or improve clarity while preserving required behavior, evaluate those candidates against the baseline, reject unsafe regressions, and recommend a non-dominated candidate only when evidence supports the recommendation.

Current implementation documentation lives in:

- [`docs/guides/semantic-optimization.md`](../docs/guides/semantic-optimization.md) — human-facing operating model and limitations;
- [`docs/design/architecture.md`](../docs/design/architecture.md) — causal flow and implementation boundaries;
- [`.ai/skills/semantic-optimization-review/SKILL.md`](../.ai/skills/semantic-optimization-review/SKILL.md) — agent review procedure.

## 2. Acceptance rule

A capability counts as implemented only when it exists in a production execution path and causally affects behavior.

A Protocol, adapter, class, CLI option, config field, injected fake, metadata field, or green line-coverage number is not sufficient evidence by itself.

The branch MUST be judged against the acceptance intent that existed on `main`, not against a weaker self-certified replacement written by the implementation PR.

Prefer completing and hardening the existing causal path over adding new abstractions.

## 3. Implemented and accepted in the current branch

The following v0.3 capabilities are implemented and SHOULD NOT be redesigned merely to make the specification look more complete.

### 3.1 Production semantic stack

The adaptive CLI/runtime path can construct a provider-neutral semantic stack from `AI_DOC_SEMANTIC_COMMAND`.

The production boundary wires:

- semantic candidate generation;
- semantic invariant discovery;
- semantic invariant verification;
- semantic evaluation when deep evaluation is enabled;
- eligible prompt suboptimization when GEPA is enabled;
- request, input-token, output-token, and USD budget configuration.

Provider-specific SDK objects remain outside optimizer domain models. Normal CI uses deterministic fake providers and does not require paid network calls.

### 3.2 Semantic generation and adaptive search inputs

Production semantic generation can affect candidate content in adaptive modes.

The provider request receives:

- current documentation;
- extracted invariants;
- generation strategy;
- previous candidate summaries;
- explored transformations;
- structured parent feedback;
- search memory.

Tests prove that feedback and search-memory contents can affect the production adapter request/result rather than existing only as placeholder parameters.

Deterministic generation remains available for conservative/offline operation.

### 3.3 Semantic evaluation and causal repair

`SearchController` consumes `EvaluationSuite` and evaluation evidence affects candidate status and objective values.

Implemented behavior includes:

- per-scenario semantic evaluation;
- task-selected effective context;
- evaluation-derived structured feedback;
- feedback-driven repair child generation;
- child re-evaluation;
- persisted feedback evidence;
- semantic reliability remaining unavailable when semantic evidence is unavailable.

The fail → feedback → repair → re-evaluate path is behaviorally tested.

### 3.4 Critical invariant safety

Critical behavior has complementary deterministic and semantic safety layers.

Implemented behavior includes:

- deterministic extraction for explicit normative language;
- semantic discovery of critical behavior without magic normative keywords;
- semantic verification of candidate behavior;
- provenance/evidence/rationale on semantic discoveries;
- preserved/weakened/removed/uncertain semantic statuses;
- rejection of critical behavior that is not semantically preserved;
- semantic verification of the whole candidate even when the original literal sentence still survives, so contradictory text elsewhere cannot bypass verification;
- deduplication between literal and semantic discoveries.

Meaning-preserving rewrites, weakening, removal/contradiction behavior, implicit critical discovery, and provenance have focused coverage.

### 3.5 Context-selection boundary

The optimizer distinguishes the full documentation corpus from task-selected effective context.

The deterministic selector starts from always-loaded instruction/skill documents and only makes reference documents reachable through explicit task-relevant routing semantics. Target-document vocabulary overlap alone does not create reachability.

Implemented tests cover:

- explicitly routed reference selection;
- unrelated reference exclusion;
- keyword-overlap anti-gaming;
- extracted reference reachability;
- repair preserving useful context savings.

Perfect simulation of every coding agent remains a non-goal.

### 3.6 Pareto, baseline, and recommendation behavior

The existing Pareto implementation remains in place.

Implemented behavior includes:

- baseline participation in comparison;
- baseline legitimately winning after semantic candidates were evaluated;
- no recommendation when replacement evidence is insufficient;
- recommendation requiring at least one material objective improvement in addition to configured regression tolerances;
- inspectable recommendation/no-change reasoning.

### 3.7 Usage telemetry and budget model

Provider usage is normalized at the production boundary and can report:

- requests;
- input tokens;
- output tokens;
- USD cost;
- cost source;
- cache hits.

Candidate/run accounting distinguishes generation, evaluation/safety work, and prompt-suboptimizer work sufficiently for the current implementation, while deterministic transformations consume zero external usage.

Request budgets are pre-call enforceable. Token/USD budgets use truthful accumulated provider usage: when the next call cannot be predicted, one completed call may report an overrun; that overrun must remain visible and later paid work must stop once exhaustion is known.

The CLI production stack wires all configured request/input/output/USD limits into the budget wrapper.

### 3.8 GEPA production integration

When GEPA is enabled and an eligible `<!-- ai-doc:gepa -->` artifact exists, the production prompt-suboptimizer boundary can modify candidate content.

Its result is not exempt from invariant/evaluation/recommendation safety. Harmful GEPA output can be rejected by the common candidate gates.

When no eligible artifact exists, the run reports a truthful no-op instead of claiming optimization occurred.

### 3.9 Evidence artifacts

The branch persists the existing run/candidate artifacts and extends semantic evidence sufficiently to inspect:

- proposal and diff;
- evaluation results;
- effective context;
- parent lineage;
- search memory;
- feedback used by a repair child;
- invariant decisions;
- usage telemetry;
- recommendation/no-change reasoning.

## 4. Known blocking gap A — budget exhaustion must terminate normally from every external stage

### Problem

The production budget wrapper correctly prevents a new provider invocation after accumulated request/token/USD exhaustion is known.

However, the search pipeline does not yet guarantee that `SemanticBudgetExceeded` is converted into a normal budget stop from every external stage.

A provider overrun can occur during semantic invariant discovery, generation, invariant verification, GEPA, or evaluation. If the next external operation is attempted before `SearchController` reaches one of its normal budget checkpoints, the wrapper can raise `SemanticBudgetExceeded`. That exception may escape the search controller and be converted by the CLI into a generic exit-1 failure rather than a completed run with a truthful `stopped_*_budget` reason and persisted telemetry.

The existing integration test proves the favorable case where an overrun occurs during baseline evaluation and the controller reaches its next budget checkpoint. It does not prove the property for every external stage.

### Required behavior

Known budget exhaustion MUST be a normal search termination condition, not an internal/configuration failure.

For every external semantic stage:

- already-completed provider usage, including an unavoidable one-call overrun, MUST remain accounted;
- no later external call may start once exhaustion is known;
- the search MUST terminate with the appropriate inspectable budget stop reason;
- run/report artifacts MUST still be persisted through the normal CLI path;
- the CLI MUST NOT convert ordinary budget exhaustion into generic exit code 1.

The implementation MAY centralize provider-budget exception handling or use another clean mechanism, but SHOULD NOT duplicate broad try/except blocks around every call if a single causal boundary is clearer.

### Acceptance tests

Add behavioral coverage for at least:

1. token/USD overrun during semantic invariant discovery followed by an attempted baseline evaluation;
2. exhaustion before generation/GEPA/evaluation prevents the downstream call;
3. the CLI completes the run path and writes run/report artifacts with the correct budget stop reason rather than exiting as an internal error;
4. telemetry includes the call that caused the unavoidable overrun.

## 5. Known blocking gap B — known Tier-0 failure must precede unnecessary GEPA work

### Problem

The current generation pipeline can invoke `_apply_gepa()` before the candidate reaches deterministic static/invariant candidate evaluation.

That means a generated candidate that is already known to violate a cheap hard constraint may still consume a prompt-suboptimizer request before rejection.

This violates the intended rule:

> Once a hard rejection is already known, unnecessary downstream semantic evaluation or prompt suboptimization must not run for that candidate.

The rule does NOT mean that every Tier-0 rejection must perform zero provider calls. Semantic invariant verification can itself be required to establish safety. It means that work whose result cannot rescue an already-known hard rejection must not be performed.

### Required behavior

Reorder or stage candidate processing so that cheap known hard failures are established before unnecessary GEPA work.

A valid implementation should preserve the principle:

`generate/materialize → cheap deterministic gates → required safety checks → optional GEPA → re-run applicable gates → semantic evaluation`

The exact decomposition may differ if a cleaner causal pipeline is available.

If GEPA changes candidate content after an initial gate, all applicable safety/static gates MUST be applied to the GEPA result before it can survive.

### Acceptance tests

- a candidate with a deterministic hard failure is rejected without invoking GEPA;
- a GEPA-produced candidate is checked again after GEPA mutation;
- a harmful GEPA rewrite is rejected by the common safety/evaluation path;
- GEPA request/token/USD accounting remains separate and truthful when GEPA actually runs.

## 6. Known blocking gap C — semantic invariant discovery needs core-side grounding against provider over-promotion

### Problem

The current semantic invariant service filters provider output by provider-declared importance, confidence, evidence, and rationale.

That is useful, but the core still trusts the provider to decide that an assertion is `critical`. A malicious, confused, or over-eager provider can label ordinary descriptive text as critical with high confidence and non-empty evidence/rationale.

The existing ordinary-text test mainly proves that ordinary text is ignored when the fake provider itself labels it non-critical. It does not prove that the optimizer resists provider over-promotion.

The original v0.3 intent requires semantic discovery to avoid converting ordinary documentation into critical invariants through evidence/severity rules that are explainable and testable outside provider self-assertion.

### Required behavior

Add conservative core-side grounding for semantic invariant discoveries.

At minimum, a semantic discovery SHOULD be validated against repository-owned source material before becoming a hard critical invariant. Suitable checks may include:

- `source_path` resolves to a document in the supplied snapshot;
- evidence is grounded in that source document or source section rather than hallucinated;
- provenance is internally consistent;
- obviously malformed or ungrounded discoveries are rejected or downgraded;
- provider confidence alone is not sufficient to create a hard critical invariant.

Do not attempt to solve universal semantic severity classification with another large framework. The goal is a conservative trust boundary around provider output.

### Acceptance tests

- provider returns an ordinary descriptive sentence as `critical`, confidence `0.99`, with plausible-looking metadata: the core does not blindly promote it to a hard invariant;
- provider returns a critical invariant with nonexistent `source_path`: reject/downgrade it;
- provider returns evidence not grounded in the claimed source: reject/downgrade it;
- a genuinely grounded implicit critical instruction still passes discovery and remains protected;
- explainable provenance survives for accepted semantic invariants.

## 7. Known acceptance gap D — prove the actual Typer CLI path end to end

### Problem

Current tests separately prove:

- `_build_semantic_stack()` wires the production semantic provider and budgets;
- production adapters work together when manually assembled around `SearchController`;
- the fake command provider exercises the real command adapter.

This gives strong wiring evidence, but it stops short of invoking the actual `ai-doc optimize` Typer command with the production semantic environment and asserting the resulting run artifacts/exit semantics.

This matters especially because CLI-level exception handling and artifact writing are part of blocking gap A.

### Required behavior

Add at least one CLI-level integration test using `CliRunner` or the repository's existing CLI test mechanism.

The test MUST use the same production semantic command adapter used outside tests, backed by a deterministic fake subprocess/provider command.

It SHOULD prove in one operator-visible path that:

- `AI_DOC_SEMANTIC_COMMAND` activates the semantic stack;
- adaptive optimization actually invokes production semantic work;
- artifacts are written;
- normal completion/no-change/budget-stop exit semantics are truthful.

No paid/network provider calls may be required.

## 8. Non-blocking cleanup and precision items

These items are not by themselves v0.3 merge blockers unless implementation work exposes a behavioral defect.

### 8.1 Recommendation evidence model

`CandidateEvidence.recommendation_reason` currently carries the behaviorally relevant explanation. If a separate recommendation-evidence domain model remains unused, either wire it when useful or remove it later rather than preserving dead symmetry.

Do not refactor this solely for aesthetic reasons during the blocking fixes.

### 8.2 Semantic safety usage categorization

Semantic invariant discovery/verification currently shares accounting territory with evaluation/safety work. Total usage is truthful, but category naming can be more precise.

A future cleanup MAY introduce an explicit invariant/safety request/token bucket, or documentation MUST clearly state that invariant semantic work belongs to the evaluation/safety bucket.

Do not delay v0.3 solely to add another cost model if aggregate and existing required category accounting remain truthful.

## 9. Preserved acceptance properties

While closing the gaps above, the following MUST remain true:

- deterministic work consumes zero external request/token/USD usage;
- baseline remains a real competitor and may win;
- recommendation requires evidence and at least one material objective improvement;
- semantic reliability is not fabricated when semantic evaluation did not run;
- semantic evaluation remains per-scenario;
- task context requires explicit routing rather than target keyword overlap;
- weakening/removal/contradiction/uncertainty of critical behavior rejects the candidate;
- semantic generation continues to receive real feedback and search memory;
- GEPA remains a suboptimizer rather than replacing outer search/Pareto control;
- no eligible GEPA artifact remains a truthful no-op;
- provider-reported/estimated usage remains visible and distinguishable from deterministic work;
- normal CI uses fake providers and makes no paid calls;
- cross-platform tests, Ruff, quality contracts, strict mypy, branch coverage, Pylint, and packaging smoke remain green.

## 10. Definition of Done

Semantic Core v0.3 is complete only when all of the following are true on the same branch head:

- the production semantic generation/evaluation/invariant/GEPA path remains behaviorally wired;
- blocking gap A is closed: budget exhaustion from every external stage becomes a normal persisted budget stop;
- blocking gap B is closed: known cheap hard failures prevent unnecessary GEPA/downstream external work and post-GEPA content is re-gated;
- blocking gap C is closed: semantic invariant discovery has a conservative core-side grounding boundary and adversarial over-promotion tests;
- acceptance gap D is closed: the actual CLI optimize path is exercised end to end with the production command adapter and deterministic fake provider;
- request/token/USD telemetry remains truthful under normal usage and unavoidable post-call overrun;
- artifacts preserve enough evidence to explain feedback, invariant decisions, effective context, telemetry, rejection, recommendation, or no-change;
- context-selection anti-gaming and repair-context-savings tests remain green;
- baseline-win and no-fabricated-reliability regressions remain green;
- GEPA eligible/ineligible/regression behaviors remain green;
- all quality/platform/packaging CI is green;
- normal CI performs no paid network calls.

Only after these conditions are demonstrated should this file's status change to `implementation complete` and the PR be marked ready for merge.

## 11. Final engineering constraint

Do not reopen already accepted semantic-loop, Pareto, packaging, or framework work without evidence of a defect.

The remaining work is narrow and behavioral:

1. make budget exhaustion a truthful normal stop everywhere;
2. prevent avoidable GEPA work after known hard rejection;
3. harden the semantic-invariant trust boundary;
4. prove the real CLI operator path.

Prefer closing those four causal gaps over introducing new architecture.