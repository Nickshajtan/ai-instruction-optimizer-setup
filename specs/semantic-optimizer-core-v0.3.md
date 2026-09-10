# AI Documentation Optimizer — Semantic Core v0.3

Status: implementation complete

## 1. Purpose

This document is the acceptance record for Semantic Core v0.3.

The product goal is:

> Given AI-facing repository documentation, produce candidate documentation changes that reduce context cost and/or improve clarity while preserving required behavior, evaluate those candidates against the baseline, reject unsafe regressions, and recommend a non-dominated candidate only when evidence supports the recommendation.

Current implementation documentation lives in:

- [`docs/guides/semantic-optimization.md`](../docs/guides/semantic-optimization.md) — human-facing operating model and limitations;
- [`docs/design/architecture.md`](../docs/design/architecture.md) — causal flow and implementation boundaries;
- [`.ai/skills/semantic-optimization-review/SKILL.md`](../.ai/skills/semantic-optimization-review/SKILL.md) — agent review procedure.

## 2. Acceptance rule

A capability counts as implemented only when it exists in a production execution path and causally affects behavior.

A Protocol, adapter, class, CLI option, config field, injected fake, metadata field, or green line-coverage number is not sufficient evidence by itself.

Semantic Core v0.3 is accepted because the required behavior is wired through the production optimizer path and covered by behavioral tests using deterministic fake providers rather than paid network calls.

## 3. Accepted capabilities

### 3.1 Production semantic stack

The adaptive CLI/runtime path constructs a provider-neutral semantic stack from `AI_DOC_SEMANTIC_COMMAND` and wires:

- semantic candidate generation;
- semantic invariant discovery;
- semantic invariant verification;
- semantic evaluation when deep evaluation is enabled;
- eligible prompt suboptimization when GEPA is enabled;
- request, input-token, output-token, and USD budget configuration.

Provider-specific SDK objects remain outside optimizer domain models. Normal CI uses deterministic fake providers.

### 3.2 Semantic generation and adaptive search inputs

Production semantic generation can affect candidate content in adaptive modes. Provider requests receive current documentation, extracted invariants, generation strategy, previous candidate summaries, explored transformations, structured parent feedback, and search memory.

Deterministic generation remains available for conservative/offline operation.

### 3.3 Semantic evaluation and causal repair

`SearchController` consumes `EvaluationSuite`; evaluation evidence affects candidate status and objective values. Per-scenario evaluation, task-selected effective context, feedback-driven repair, child re-evaluation, persisted feedback evidence, and no-fabricated semantic reliability are preserved.

### 3.4 Critical invariant safety

Critical behavior has complementary deterministic and semantic safety layers:

- explicit normative language is extracted deterministically;
- implicit critical behavior can be discovered semantically;
- semantic discoveries are accepted only through a conservative repository-grounded trust boundary;
- candidate behavior is semantically verified when required;
- preserved/weakened/removed/uncertain decisions remain inspectable;
- weakening, removal, contradiction, or uncertainty rejects critical behavior;
- semantic verification checks the whole candidate rather than treating surviving literal wording as sufficient proof;
- literal and semantic discoveries are deduplicated.

### 3.5 Context-selection boundary

The optimizer distinguishes the full documentation corpus from task-selected effective context. Always-loaded instruction/skill documents form the starting set; reference documents become reachable only through explicit task-relevant routing semantics. Target-document vocabulary overlap alone does not create reachability.

### 3.6 Pareto, baseline, and recommendation behavior

Baseline remains a real competitor and may win. Recommendation requires inspectable evidence, configured regression tolerance, and at least one material objective improvement. Insufficient evidence results in a truthful no-change outcome.

### 3.7 Usage telemetry and budget model

Provider usage is normalized at the production boundary and records requests, input tokens, output tokens, USD cost, cost source, and cache hits.

Generation, evaluation/safety work, and prompt-suboptimizer work remain distinguishable. Deterministic transformations consume zero external usage.

Request budgets are pre-call enforceable. Token/USD accounting uses truthful accumulated provider usage. An unavoidable completed call may cross a configured token/USD threshold; that overrun remains visible and later paid work is stopped once exhaustion is known.

### 3.8 GEPA production integration

When GEPA is enabled and an eligible `<!-- ai-doc:gepa -->` artifact exists, the production prompt-suboptimizer may modify candidate content. GEPA remains subordinate to the outer search and common safety gates.

When no eligible artifact exists, the run reports a truthful no-op.

### 3.9 Evidence artifacts

Run/candidate artifacts preserve proposal/diff, evaluation results, effective context, lineage, search memory, repair feedback, invariant decisions, usage telemetry, and recommendation/no-change reasoning.

## 4. Closure of former acceptance gaps

### 4.1 Gap A — budget exhaustion from every external stage

Closed.

Known budget exhaustion is handled as a normal search termination condition rather than a generic internal failure. Completed provider usage, including unavoidable one-call token/USD overruns, is retained; downstream external work is prevented once exhaustion is known; the run receives an inspectable `stopped_*_budget` reason and budget stage; and the normal CLI path persists run/report artifacts.

Behavioral coverage includes baseline evaluation overrun, generation exhaustion before GEPA, GEPA exhaustion before downstream invariant verification, and CLI-level discovery overrun persistence.

Primary coverage:

- `tests/integration/test_semantic_budget_overrun.py`
- `tests/integration/test_semantic_cli_e2e.py`

### 4.2 Gap B — known Tier-0 failure before unnecessary GEPA work

Closed.

Candidate processing now follows the intended causal ordering:

`generate/materialize → cheap deterministic gates → required safety checks → optional GEPA → re-run applicable cheap gates → semantic evaluation`

Before GEPA, the optimizer rejects both newly introduced static hard failures and deterministic regressions of literal critical invariants. The pre-GEPA invariant gate deliberately considers only repository-owned literal invariants; semantic discoveries are not converted into exact-text requirements and continue through semantic verification.

After GEPA mutation, applicable cheap deterministic gates are run again before the candidate can proceed. The full semantic invariant/evaluation path remains authoritative for semantic safety.

Primary coverage:

- `tests/integration/test_gepa_gate_order.py`
- `tests/integration/test_gepa_regression_rejection.py`

### 4.3 Gap C — core-side grounding against semantic invariant over-promotion

Closed.

Provider declarations cannot create a hard critical invariant from confidence/severity metadata alone. Semantic discoveries require repository-owned source grounding, source-path validity, grounded evidence, provenance/rationale, and a criticality cue in the grounded source evidence.

Primary coverage:

- `tests/unit/test_semantic_invariant_discovery.py`

### 4.4 Gap D — actual Typer CLI path end to end

Closed.

`tests/integration/test_semantic_cli_e2e.py` invokes the real `ai-doc optimize` Typer command with `AI_DOC_SEMANTIC_COMMAND` pointing to the deterministic subprocess fixture used by the production `CommandSemanticProvider` boundary.

The test proves production semantic activation, semantic usage, artifact creation, deterministic no-change exit semantics, and persisted budget-stop behavior without paid/network calls.

## 5. Preserved acceptance properties

The following remain part of the v0.3 contract:

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
- cross-platform tests, Ruff, quality contracts, strict mypy, branch coverage, Pylint, and packaging smoke remain release gates.

## 6. Definition of Done

Semantic Core v0.3 is complete when the following hold on the same branch head:

- production semantic generation/evaluation/invariant/GEPA paths are behaviorally wired;
- budget exhaustion is a normal persisted stop across external stages;
- known cheap hard failures prevent unnecessary GEPA/downstream work;
- post-GEPA content is re-gated;
- semantic invariant discovery has a conservative core-side grounding boundary;
- the actual CLI optimize path is exercised end to end with the production command adapter and deterministic fake provider;
- request/token/USD telemetry remains truthful under normal usage and unavoidable post-call overrun;
- artifacts preserve enough evidence to explain feedback, invariant decisions, effective context, telemetry, rejection, recommendation, or no-change;
- context-selection anti-gaming and repair-context-savings tests remain green;
- baseline-win and no-fabricated-reliability regressions remain green;
- GEPA eligible/ineligible/regression behaviors remain green;
- quality/platform/packaging CI remains green;
- normal CI performs no paid network calls.

The implementation and behavioral coverage now satisfy this acceptance contract. Future changes should treat this file as the v0.3 completion record rather than a remaining-work queue.

## 7. Final engineering constraint

Do not reopen the accepted semantic loop, Pareto, packaging, or framework work without evidence of a defect.

Future work should build on the established production boundaries and preserve the causal acceptance properties above.