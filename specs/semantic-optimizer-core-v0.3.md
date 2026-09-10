# AI Documentation Optimizer — Semantic Core v0.3

Status: implementation complete; final CI/merge validation applies

## Purpose

This file was the remaining-work implementation specification for Semantic Core v0.3. The implementation items previously listed here have been completed in this branch, so there is no remaining v0.3 implementation backlog in this document.

Current behavior is documented in:

- [`docs/guides/semantic-optimization.md`](../docs/guides/semantic-optimization.md) — human-facing operating model and limitations;
- [`docs/design/architecture.md`](../docs/design/architecture.md) — causal flow and implementation boundaries;
- [`.ai/skills/semantic-optimization-review/SKILL.md`](../.ai/skills/semantic-optimization-review/SKILL.md) — agent review procedure.

## Acceptance Contract

The milestone is considered complete only while the following remain true:

- the normal adaptive CLI/runtime path can construct the provider-neutral semantic stack from `AI_DOC_SEMANTIC_COMMAND`;
- semantic generation receives real feedback and search-memory contents, not placeholder presence flags;
- critical behavior can be discovered semantically with inspectable source/evidence/rationale provenance;
- ordinary descriptive provider output is not automatically promoted to a critical invariant;
- literal survival of a critical sentence does not bypass semantic contradiction checking when semantic verification is configured;
- weakened, removed, contradicted, or uncertain critical behavior rejects the candidate;
- request, input-token, output-token, and USD limits are wired to the production provider budget wrapper;
- known accumulated budget exhaustion prevents another external invocation;
- when a provider call cannot be predicted and reports a token/USD overrun after execution, the overrun is retained truthfully and later external work stops;
- deterministic work consumes zero external request/token/USD usage;
- eligible prompt suboptimization has no safety bypass and a harmful provider-produced rewrite can be rejected by common gates;
- semantic evaluation remains per-scenario and uses task-selected effective context;
- explicit task-relevant routing is required for on-demand reference reachability rather than target-document vocabulary overlap alone;
- failed semantic evaluation can causally produce feedback, a repair child, and re-evaluation while preserving useful context savings/reachability;
- baseline remains a real competitor and may legitimately win;
- recommendation requires material objective improvement in addition to configured tolerances;
- selected-candidate or no-change evidence names concrete recommendation factors;
- semantic reliability is unavailable when semantic evaluation evidence is unavailable;
- normalized provider usage remains separated into generation, evaluation, and prompt-suboptimizer work;
- normal CI uses deterministic fake providers and makes no paid network calls;
- Ruff, quality contracts, strict mypy, branch coverage, Pylint, platform tests, and packaging smoke remain green.

## Budget Semantics

Token/USD budgets are accumulated provider-boundary controls, not an invented strict reservation guarantee.

If a provider or adapter has a trustworthy estimate for the next call, it may reject the call before execution when the estimate exceeds the remaining budget. If the next call cannot be predicted truthfully, one call may report usage beyond the remaining token/USD budget. That usage must remain visible and no later external work may start after exhaustion is known.

Request budgets remain pre-call enforceable because the next invocation itself is countable.

## Tier-0 Provider-Call Semantics

A blanket rule that every Tier-0 rejection performs zero provider calls is intentionally not part of the contract. Semantic invariant verification can itself be required to determine safety.

The intended rule is narrower: once a hard rejection is already known, unnecessary downstream semantic evaluation or prompt suboptimization must not run for that candidate.

## Scope Limits

Semantic Core v0.3 does not claim:

- perfect simulation of Claude, Codex, Copilot, or another coding agent's context-loading behavior;
- automatic application of generated patches;
- universal hosted-provider SDK support;
- exact provider billing when the configured command reports estimates rather than provider-native usage;
- strict pre-reservation of unknown future token/USD cost.

Those are not hidden incomplete v0.3 capabilities. Future work should be specified separately rather than reopening this milestone by default.

## Regression Rule

A Protocol, adapter, class, CLI option, or green line-coverage number is not sufficient evidence of capability by itself. If a future change breaks one of the acceptance properties above, treat it as a regression even if the public shape of the subsystem still exists.

Prefer adversarial behavioral tests that fail when the causal property is broken.
