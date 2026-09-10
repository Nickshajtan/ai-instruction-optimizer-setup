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
- `specs/semantic-optimizer-core-v0.3.md` for the remaining milestone blockers only;
- `docs/standards.md` for normative project rules.

Do not infer unfinished work from an older architectural model. Production semantic generation, semantic invariant discovery/verification, eligible prompt suboptimization, normalized usage telemetry, effective-context evidence, and repair evidence are now wired capabilities when the semantic command is configured. The remaining-work spec is authoritative for what is still incomplete.

## Review Order

Do not rank candidates by token count alone. Review evidence in this order:

1. Check candidate status and rejection reasons.
2. Inspect semantic scenario results when semantic evaluation ran.
3. Inspect critical invariant preservation and any safety-sensitive changes.
4. Read `diff.patch` and verify that routing remains understandable and actionable.
5. Compare always-loaded and expected task-context cost with baseline.
6. Inspect Pareto-frontier membership and the trade-offs that keep the candidate non-dominated.
7. Inspect external usage/cost evidence when semantic providers ran.
8. Treat the recommendation as evidence-backed advice, not automatic permission to apply the candidate.

## Evidence Rules

- Treat baseline as a real competitor. "No change" is a valid outcome.
- A generated candidate must materially improve at least one recommendation dimension; being merely inside regression tolerances is not an improvement.
- Do not call lexical Promptfoo `echo + contains/not-contains` checks semantic evidence.
- Do not fabricate semantic reliability when no semantic evaluator ran.
- Distinguish the full documentation corpus from task-selected effective context.
- The deterministic context selector requires explicit task-relevant routing from reachable context; still treat it as an approximation, not proof that a real agent will load exactly the same files.
- Do not treat a Protocol, adapter seam, or test double as a production capability unless the normal product path wires it and its output causally affects the result.
- Production semantic work can be supplied through `AI_DOC_SEMANTIC_COMMAND`; provider SDK objects remain outside optimizer domain models.
- Request/token/USD usage may be provider-reported or explicitly estimated. Inspect cost provenance before treating it as exact.
- Current request-budget wiring is stronger than token/USD budget wiring. Until the remaining v0.3 budget work is complete, do not claim strict provider-boundary token/USD enforcement.
- A literal copy of a critical invariant is not sufficient evidence against a contradictory exception elsewhere. This is a known remaining safety gap until contradiction-safe verification is completed.
- GEPA/prompt-suboptimizer metadata can report either performed work or a truthful no-op. Verify the eligible artifact and changed candidate before describing prompt optimization as effective.

## Repair-Loop Review

When a child candidate claims to repair an evaluation failure, verify the causal chain rather than only the final state:

1. identify the parent failure;
2. confirm structured feedback was derived from actual evaluation evidence;
3. confirm the child mutation addresses that feedback;
4. confirm the child was evaluated again;
5. confirm the repair did not destroy the original context-cost benefit or make extracted documentation unreachable.

Persisted candidate evidence can now contain the feedback used to produce the repair child. Prefer that evidence over reconstructing the chain from logs.

## Invariant Review

For critical invariants:

- inspect whether the invariant came from literal or semantic discovery when that provenance is available;
- inspect `invariant_decisions` in candidate evidence;
- search the entire candidate for weakening, exceptions, or contradictions rather than trusting literal preservation alone;
- treat weakened, removed, contradicted, or uncertain critical behavior as unsafe;
- flag semantic discoveries whose criticality cannot be explained from the source text/evidence.

Semantic discovery rationale/provenance is still being hardened for v0.3, so distinguish provider classification from independently inspectable justification.

## Artifact Map

Typical run artifacts:

- `run.json` — complete run model, total usage, recommendation/no-change result, and metadata;
- `report.json` — operator-facing aggregate result;
- `frontier.json` — non-dominated candidates;
- `lineage.json` — parent/child relationships;
- `search-memory.json` — accumulated search state;
- `candidates/<id>/proposal.json` — proposed operations;
- `candidates/<id>/candidate/` — rendered candidate documentation;
- `candidates/<id>/diff.patch` — human-reviewable changes;
- `candidates/<id>/evaluation.json` — evaluation evidence when present;
- `candidates/<id>/evidence.json` — generation rationale, repair feedback, invariant decisions, and effective-context evidence.

Current evidence is sufficient to reconstruct much of a run without rerunning it. Recommendation/no-change explanation is still coarse and semantic invariant discovery needs stronger persisted rationale/provenance; both remain v0.3 work.

## Red Flags

Escalate when any of these appear:

- lower token cost is presented as sufficient evidence of improvement;
- semantic reliability exists without semantic evaluation evidence;
- scenario requirements leak across unrelated tasks;
- a reference is considered reachable without an explicit task-relevant route from reachable context;
- a critical behavior disappears because it lacked explicit MUST/NEVER-style wording;
- literal critical wording remains but another section adds an opposing exception;
- token/USD limits are described as strict pre-call guarantees without provider-boundary evidence;
- an adapter reports work as performed when it actually no-oped;
- a repaired child passes but loses the context saving that justified its parent direction;
- baseline could reasonably win but recommendation forces a generated candidate;
- a recommendation reason is generic enough that its material improvement cannot be identified from persisted objectives/policy.

## Output Expectation

When reporting a review, distinguish clearly between:

- confirmed behavior supported by persisted evidence;
- plausible but unproven behavior;
- known implementation limitation;
- actual defect or unsafe optimization.

Prefer concrete counterexamples and evidence paths over generic architectural advice.
