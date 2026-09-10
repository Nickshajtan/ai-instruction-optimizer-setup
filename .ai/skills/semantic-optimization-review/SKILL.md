---
name: "ai-doc-semantic-optimization-review"
description: "Review ai-doc semantic optimization runs using evidence, safety invariants, task-selected context, Pareto trade-offs, and baseline comparison."
version: 1
---

# Semantic Optimization Review

Use this skill when an agent is asked to inspect, explain, validate, or critique an `ai-doc optimize` run.

## Required Context

Read `docs/guides/semantic-optimization.md` first. For implementation changes also read `docs/design/architecture.md`, `specs/semantic-optimizer-core-v0.3.md`, and `docs/standards.md`.

Do not infer capability from interfaces alone. Require a production execution path plus behavioral evidence.

## Review Order

1. Check run stop reason, `metadata.budget_stop_stage`, candidate status, and rejection reasons.
2. Inspect semantic scenario results when semantic evaluation ran.
3. Inspect critical invariant discovery provenance and candidate invariant decisions.
4. Verify accepted semantic discoveries are grounded in the claimed repository source/evidence, not only provider severity/confidence.
5. Read `diff.patch` and verify routing remains understandable/actionable.
6. Compare always-loaded and expected task-context cost with baseline.
7. Inspect Pareto membership and the trade-offs keeping the candidate non-dominated.
8. Inspect external request/token/USD usage and cost provenance; for multiple scenarios verify usage represents all scenario calls.
9. Inspect concrete recommendation/no-change evidence.
10. Treat recommendation as evidence-backed advice, not permission to apply automatically.

## Evidence Rules

- Baseline is a real competitor; no-change is valid.
- A recommendation needs material improvement, not merely tolerance compliance.
- Do not call lexical Promptfoo echo/contains checks semantic evidence.
- Do not fabricate reliability when no semantic evaluator ran.
- Distinguish full corpus from task-selected effective context.
- Explicit-route context selection is still an approximation of real Claude/Codex/Copilot loading behavior.
- Semantic provider evidence is only as trustworthy as the configured `AI_DOC_SEMANTIC_COMMAND` contract.
- Semantic invariant provider output is additionally subject to a core grounding boundary: real source path, repository-grounded evidence, and a critical instruction/safety cue in that evidence. A provider-authored MUST summary is not enough.
- Request/token/USD limits are accumulated provider-boundary controls. Without a trustworthy pre-call estimate, one completed call may report an overrun; verify that the usage is retained, the run stops normally, and no later external work begins after exhaustion is known.
- For a budget-stopped run, require `run.json`/`report.json` plus an appropriate `stopped_*_budget` reason rather than treating ordinary exhaustion as an internal error.
- Literal survival of a critical rule is not conclusive when semantic verification is configured. Inspect the global semantic decision for contradictory exceptions.
- A known cheap static hard failure must reject before GEPA. If GEPA changes content, the changed tree must be gated again before later semantic work.
- GEPA has no safety bypass: its output must survive the same applicable static, invariant, and evaluation gates.

## Repair-Loop Review

For a repair child, verify parent failure -> structured feedback -> child mutation -> re-evaluation -> retained context saving/reachability. Prefer persisted feedback evidence over reconstructing the chain from logs.

## Artifact Map

- `run.json` — run model, candidates, total usage, recommendation/no-change result, stop reason, metadata;
- `report.json` — operator-facing aggregate result;
- `frontier.json` — non-dominated candidates;
- `lineage.json` — parent/child relationships;
- `search-memory.json` — accumulated search state;
- `candidates/<id>/proposal.json` — proposed operations;
- `candidates/<id>/candidate/` — rendered documentation;
- `candidates/<id>/diff.patch` — human-reviewable changes;
- `candidates/<id>/evaluation.json` — evaluation evidence;
- `candidates/<id>/evidence.json` — generation, feedback, invariant, and context evidence written at candidate evaluation time.

Recommendation evidence is also present in final run candidate models: selected-candidate evidence names improved objectives/tolerated regressions; baseline evidence records concrete blocking factors when no candidate qualifies.

## Red Flags

Escalate when:

- lower token cost is treated as sufficient proof of improvement;
- semantic reliability exists without semantic evaluation;
- scenario requirements leak across tasks;
- multi-scenario evaluation usage looks like only one scenario was billed/accounted;
- a reference is reachable only by vocabulary overlap rather than an explicit task-relevant route;
- implicit critical behavior disappears because it lacked MUST/NEVER wording;
- an alleged semantic critical invariant cites a nonexistent source or evidence absent from that source;
- ordinary descriptive evidence becomes critical only because the provider adds normative wording in its summary;
- literal critical wording survives while another section contradicts it and semantic verification still reports preserved;
- a known exhausted provider budget is followed by more external work or becomes generic CLI exit 1 without normal run artifacts;
- GEPA runs for a candidate already known to fail a cheap static hard gate;
- post-GEPA content is not re-gated;
- an adapter reports work as performed when it no-oped;
- a repaired child loses the context saving/reachability that justified the direction;
- recommendation forces a generated candidate when baseline should win;
- recommendation evidence cannot identify the material improvement or blocking factor.

## Output Expectation

Distinguish confirmed persisted evidence, plausible but unproven behavior, documented limitation, and actual defect. Prefer concrete counterexamples and artifact paths over generic architectural advice.
