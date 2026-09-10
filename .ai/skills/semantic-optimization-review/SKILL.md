---
name: "ai-doc-semantic-optimization-review"
description: "Review ai-doc semantic optimization runs using evidence, safety invariants, task-selected context, Pareto trade-offs, and baseline comparison."
version: 1
---

# Semantic Optimization Review

Use this skill when an agent is asked to inspect, explain, validate, or critique the result of an `ai-doc optimize` run.

## Required Context

Read `docs/guides/semantic-optimization.md` first for the human-facing model of the optimizer and its current limitations.

If implementation changes are requested, also read:

- `docs/design/architecture.md` for the causal optimization flow and subsystem boundaries;
- `specs/semantic-optimizer-core-v0.3.md` for remaining milestone work;
- `docs/standards.md` for normative project rules.

## Review Order

Do not rank candidates by token count alone. Review evidence in this order:

1. Check candidate status and rejection reasons.
2. Inspect semantic scenario results when semantic evaluation ran.
3. Inspect critical invariant preservation and any safety-sensitive changes.
4. Read `diff.patch` and verify that routing remains understandable and actionable.
5. Compare always-loaded and expected task-context cost with baseline.
6. Inspect Pareto-frontier membership and the trade-offs that keep the candidate non-dominated.
7. Treat the recommendation as evidence-backed advice, not automatic permission to apply the candidate.

## Evidence Rules

- Treat baseline as a real competitor. "No change" is a valid outcome.
- Do not call lexical Promptfoo `echo + contains/not-contains` checks semantic evidence.
- Do not fabricate semantic reliability when no semantic evaluator ran.
- Distinguish the full documentation corpus from task-selected effective context.
- Treat deterministic context selection as an approximation of agent routing, not proof that Claude, Codex, Copilot, or another agent would load the same files.
- Do not treat a Protocol, adapter seam, or test double as a production capability unless the normal product path wires it and its output causally affects the result.
- Request counts are meaningful today; token/USD telemetry is not yet complete enough to imply precise FinOps guarantees.
- GEPA metadata may truthfully report a no-op. Do not describe that as performed prompt optimization.

## Repair-Loop Review

When a child candidate claims to repair an evaluation failure, verify the causal chain rather than only the final state:

1. identify the parent failure;
2. confirm structured feedback was derived from actual evaluation evidence;
3. confirm the child mutation addresses that feedback;
4. confirm the child was evaluated again;
5. confirm the repair did not destroy the original context-cost benefit or make extracted documentation unreachable.

A manually constructed feedback object is not evidence that the production feedback loop works.

## Artifact Map

Typical run artifacts:

- `run.json` — complete run model and metadata;
- `report.json` — operator-facing aggregate result;
- `frontier.json` — non-dominated candidates;
- `lineage.json` — parent/child relationships;
- `search-memory.json` — accumulated search state;
- `candidates/<id>/proposal.json` — proposed operations;
- `candidates/<id>/candidate/` — rendered candidate documentation;
- `candidates/<id>/diff.patch` — human-reviewable changes;
- `candidates/<id>/evaluation.json` — evaluation evidence when present.

Current artifacts do not yet persist every piece of semantic evidence. In particular, exact repair feedback, semantic invariant decisions, complete recommendation/no-change reasoning, and full provider token/USD telemetry remain milestone work.

## Red Flags

Escalate when any of these appear:

- lower token cost is presented as sufficient evidence of improvement;
- semantic reliability exists without semantic evaluation evidence;
- scenario requirements leak across unrelated tasks;
- a router appears reachable only because the deterministic selector matches surrounding keywords;
- a critical behavior disappears because it lacked explicit MUST/NEVER-style wording;
- an adapter reports work as performed when it actually no-oped;
- a repaired child passes but loses the context saving that justified its parent direction;
- baseline could reasonably win but the recommendation machinery forces a generated candidate.

## Output Expectation

When reporting a review, distinguish clearly between:

- confirmed behavior supported by persisted evidence;
- plausible but unproven behavior;
- known implementation limitation;
- actual defect or unsafe optimization.

Prefer concrete counterexamples and evidence paths over generic architectural advice.
