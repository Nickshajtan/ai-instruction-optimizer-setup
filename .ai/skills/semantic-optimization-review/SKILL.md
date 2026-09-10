---
name: "ai-doc-semantic-optimization-review"
description: "Review ai-doc semantic optimization runs using evidence, safety invariants, task-selected context, Pareto trade-offs, and baseline comparison."
version: 1
---

# Semantic Optimization Review

Use this skill when an agent is asked to inspect, explain, validate, or critique an `ai-doc optimize` run.

## Required Context

Read `docs/guides/semantic-optimization.md` first. For implementation changes also read `docs/design/architecture.md`, the still-open acceptance items in `specs/semantic-optimizer-core-v0.3.md`, and `docs/standards.md`.

Do not infer capability from interfaces alone. Production semantic generation, semantic invariant discovery/verification, eligible prompt suboptimization, normalized provider usage, effective-context evidence, and feedback-directed repair count because the normal product path wires them and tests exercise their causal behavior.

## Review Order

1. Check candidate status and rejection reasons.
2. Inspect semantic scenario results when semantic evaluation ran.
3. Inspect critical invariant discovery provenance and candidate invariant decisions.
4. Read `diff.patch` and verify routing remains understandable/actionable.
5. Compare always-loaded and expected task-context cost with baseline.
6. Inspect Pareto membership and the trade-offs keeping the candidate non-dominated.
7. Inspect external request/token/USD usage and cost provenance.
8. Inspect concrete recommendation/no-change evidence.
9. Treat recommendation as evidence-backed advice, not permission to apply automatically.

## Evidence Rules

- Baseline is a real competitor; no-change is valid.
- A recommendation needs material improvement, not merely tolerance compliance.
- Do not call lexical Promptfoo echo/contains checks semantic evidence.
- Do not fabricate reliability when no semantic evaluator ran.
- Distinguish full corpus from task-selected effective context.
- Explicit-route context selection is still an approximation of real Claude/Codex/Copilot loading behavior.
- Semantic provider evidence is only as trustworthy as the configured `AI_DOC_SEMANTIC_COMMAND` contract.
- Request/token/USD limits are accumulated provider-boundary controls. Without a trustworthy pre-call estimate, one call may report an overrun; verify that the overrun is retained and no later external work begins after the limit is known.
- Literal survival of a critical rule is not conclusive when semantic verification is configured. Inspect the global semantic decision for contradictory exceptions.
- Semantic critical discoveries should carry source location, evidence, rationale, confidence, and discovery source. Flag unexplained provider classifications.
- GEPA has no safety bypass: its output must survive the same invariant/evaluation gates.

## Repair-Loop Review

For a repair child, verify parent failure -> structured feedback -> child mutation -> re-evaluation -> retained context saving/reachability. Prefer persisted feedback evidence over reconstructing the chain from logs.

## Artifact Map

- `run.json` — run model, candidates, total usage, recommendation/no-change result, metadata;
- `report.json` — operator-facing aggregate result;
- `frontier.json` — non-dominated candidates;
- `lineage.json` — parent/child relationships;
- `search-memory.json` — accumulated search state;
- `candidates/<id>/proposal.json` — proposed operations;
- `candidates/<id>/candidate/` — rendered documentation;
- `candidates/<id>/diff.patch` — human-reviewable changes;
- `candidates/<id>/evaluation.json` — evaluation evidence;
- `candidates/<id>/evidence.json` — generation, feedback, invariant, context evidence written at candidate evaluation time.

Recommendation evidence is also present in the final run candidate models: selected-candidate evidence names improved objectives/tolerated regressions; baseline evidence records concrete blocking factors when no candidate qualifies.

## Red Flags

Escalate when:

- lower token cost is treated as sufficient proof of improvement;
- semantic reliability exists without semantic evaluation;
- scenario requirements leak across tasks;
- a reference is reachable only by vocabulary overlap rather than an explicit task-relevant route;
- implicit critical behavior disappears because it lacked MUST/NEVER wording;
- literal critical wording survives while another section contradicts it and semantic verification still reports preserved;
- a known exhausted provider budget is followed by more external work;
- an adapter reports work as performed when it no-oped;
- a repaired child loses the context saving/reachability that justified the direction;
- recommendation forces a generated candidate when baseline should win;
- recommendation evidence cannot identify the material improvement or blocking factor.

## Output Expectation

Distinguish confirmed persisted evidence, plausible but unproven behavior, documented limitation, and actual defect. Prefer concrete counterexamples and artifact paths over generic architectural advice.
