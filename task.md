# PR #31 — Second-Pass Hardening and Acceptance Fixes

Repository:

`Nickshajtan/ai-instruction-optimizer-setup`

Work on the existing PR #31 branch.

This is a **narrow second-pass review and cleanup** of the already implemented Post-Integration Core Hardening work.

Do **not** redesign the optimizer, extension system, analyzer architecture, observation system, or execution pipeline.

The first implementation pass is substantially complete. Your job now is to verify the implementation against the intended contracts, fix the concrete issues below, look for directly adjacent correctness gaps, and leave the branch in a genuinely self-consistent state.

Keep `task.md` for now. It will be removed separately after acceptance.

---

# 1. Fix incomplete pairwise observation outcome accounting

The new pairwise observation instrumentation currently records:

- `candidate_preferred`
- `baseline_preferred`
- `uncertain`

However, the actual pairwise result domain supports terminal outcomes including:

- `candidate`
- `baseline`
- `equivalent`
- `uncertain`

This means a successfully performed comparison whose overall result is `equivalent` can currently disappear from aggregate outcome accounting.

For example, this must never be possible without an explicitly documented reason:

```text
comparisons_performed = 3

candidate_preferred = 1
baseline_preferred = 0
uncertain = 1

accounted outcomes = 2
```

## Required correction

Inspect the actual `PairwiseOutcome` / `PairwiseSemanticResult` contract and make observation accounting complete.

Prefer preserving the real semantic distinction:

```text
candidate_preferred
baseline_preferred
equivalent
uncertain
```

Do **not** silently map `equivalent` to `uncertain` unless the existing domain semantics genuinely establish that equivalence.

Add a regression invariant such that, for normally completed pairwise comparisons represented by terminal results:

```text
candidate_preferred
+ baseline_preferred
+ equivalent
+ uncertain
== comparisons_performed
```

If there are legitimate cases where `comparisons_performed` can differ from the number of persisted terminal outcomes, identify that explicitly and model/test the distinction rather than hiding it.

The observation layer must continue to derive facts from authoritative run/candidate state. Do not reconstruct pairwise execution from provider request counts or cost data.

Update documentation if the observation schema description is affected.

---

# 2. Re-review `FindingAdapter` public contract

P1-2 introduced:

```python
FindingAdapter
```

into `ai_doc.api.v1`.

The current implementation appears to expose `FindingAdapter` as a public protocol while project adapters are operationally registered as analyzers and discovered through optional:

```python
adapt_findings(...)
```

on those analyzers.

This may be an acceptable minimal implementation, but verify that the public contract is coherent.

## Required review

Confirm all of the following:

1. A project extension can implement finding adaptation using only public `ai_doc.api.v1` imports.
2. It participates in the real production CLI path.
3. Built-in analyzers still execute normally.
4. Unrelated extension analyzers still execute normally.
5. Adapter execution order is deterministic.
6. Multiple adapters have deterministic composition semantics.
7. The public typing/docs accurately describe how an adapter is registered and invoked.
8. The exported `FindingAdapter` protocol is actually useful to extension authors rather than being a nominal type disconnected from the registration contract.

Do **not** introduce a new adapter registry, middleware framework, event system, hook system, or generic rules engine merely to make the abstraction prettier.

If the existing implementation is behaviorally sound, keep it small and improve only typing/tests/docs necessary to make the contract truthful.

If there is a concrete mismatch between the exported API and actual registration mechanism, fix the **smallest demonstrated gap**.

Add focused regression coverage for multiple adapters/order if it is not already covered.

---

# 3. Re-evaluate `STRUCTURE_NO_HEADINGS` false-positive risk

The new heuristic currently treats a heading-less document as substantial when roughly:

```python
token_count >= 120
or
list_items >= 3
```

The second condition is suspicious.

Three short Markdown bullets can be a perfectly legitimate small note/checklist and should not automatically produce a structural warning merely because headings are absent.

This hardening pass was specifically motivated by analyzer signal quality and false-positive reduction. Do not fix one noisy rule by introducing another noisy rule.

## Required correction

Create adversarial fixtures covering at least:

### A. Tiny legitimate checklist

Example shape:

```markdown
- Run tests.
- Update changelog.
- Open PR.
```

Expected:

`STRUCTURE_NO_HEADINGS` must **not** fire solely because there are three bullets.

### B. Small heading-less reference/note

A short coherent Markdown note with several bullets.

Expected:

No unnecessary structural warning.

### C. Substantial heading-less document

Enough structured/content volume that headings would materially improve navigation.

Expected:

`STRUCTURE_NO_HEADINGS` should fire.

### D. Existing noisy duplication case

Ensure the structural heuristic still provides useful signal where the original dogfooding case demonstrated genuinely substantial heading-less content.

Use conservative evidence already available from the parsed document.

Do not add semantic/LLM classification.

Do not add project-specific heading rules.

Do not introduce configurable thresholds unless there is demonstrated need.

Prefer a conservative heuristic with fewer false positives over maximizing finding count.

---

# 4. Fix the repository's own broken documentation link

The previous implementation report stated:

> `python -m ai_doc check . --format json --non-interactive` failed on an existing broken link in `docs/design/architecture.md` to missing `../../specs/semantic-optimizer-core-v0.3.md`, and the issue was left untouched.

Do not leave the repository in this state.

This is now part of acceptance because the repository's own production check command exposed it during validation.

Inspect the broken reference and determine the intended target.

Then make the smallest correct documentation fix:

- point it to the real existing document if the target moved or was renamed;
- remove/update the stale reference if the referenced spec no longer exists;
- do **not** create a fake placeholder spec merely to satisfy the checker.

The final repository-level command:

```bash
python -m ai_doc check . --format json --non-interactive
```

must no longer fail because of this broken internal link.

If it still returns a non-zero status for legitimate analyzer findings according to normal CLI semantics, distinguish that from an actual broken-link/integrity failure in the final report.

---

# 5. Second-pass contract review of P0-1 / P0-1A

Re-read the implementation rather than assuming the first pass is correct.

Verify these invariants end-to-end.

## Pairwise request state

```text
pairwise_semantic_requested = false
pairwise_comparisons_performed = 0
```

means pairwise was not requested.

```text
pairwise_semantic_requested = true
pairwise_comparisons_performed = 0
```

means pairwise was requested but **not judged**.

```text
pairwise_semantic_requested = true
pairwise_comparisons_performed > 0
```

means at least one actual pairwise comparison occurred.

No unrelated semantic operation may increment this counter.

## Strict mode

```bash
--require-pairwise-semantic
```

must:

- imply pairwise semantic judging;
- require at least one actual comparison;
- fail non-zero when zero comparisons occur;
- succeed with respect to this postcondition when at least one comparison occurs;
- not be satisfied by deep evaluation, semantic generation, invariant verification, GEPA, or other semantic provider activity.

## Failed/aborted comparisons

Review exactly when:

```python
pairwise_comparisons_performed += 1
```

occurs.

A comparison should count as performed only when the pairwise evaluator actually produced a valid terminal comparison result according to the domain contract.

Budget rejection before execution must not count.

Provider/runtime failure must not be transformed into a successful performed comparison.

Do not weaken existing fail-closed behavior.

---

# 6. Second-pass contract review of P0-3

Verify optimizer-owned output exclusion against path edge cases.

At minimum cover:

- default `.ai-doc-output`;
- nested files below it;
- previous optimization runs;
- explicit config with broad `**/*.md`;
- explicit config that omits default excludes;
- custom in-project `--output`;
- custom output with normalized relative paths;
- unrelated similarly named directories;
- generic Markdown discovery remaining unaffected.

Do not expand this into generalized generated-file detection.

The invariant remains:

> ai-doc optimization artifacts must not become optimization source documents merely because user configuration omitted an exclusion.

---

# 7. Do not implement the deferred gated pipeline in this pass

The deferred P2 gated-evidence/pipeline work is intentionally **not part of this cleanup**.

Do not implement:

- generic evidence-stage orchestration;
- cheapest-sufficient-evidence execution;
- new execution-policy taxonomy;
- pipeline DSL;
- stage state machine;
- cross-tool orchestration.

Leave the existing defer documentation intact unless it contains a factual error.

We will evaluate the pipeline separately after this PR is otherwise ready.

---

# Validation

Run the complete existing validation suite after the fixes.

At minimum:

```bash
python -m ruff check .
python -m pytest
python -m mypy
python -m ai_doc check . --format json --non-interactive
```

Also run any focused tests added for this second pass.

Do not merely report that commands were run. Distinguish:

- command execution success;
- test success;
- expected analyzer findings;
- actual tool/integrity failures.

The repository must not retain a known broken internal documentation link discovered by its own checker.

---

# Scope discipline

This is **not** another architecture pass.

Do not:

- redesign search;
- redesign the extension registry;
- redesign observations;
- add a generic policy engine;
- add a new pipeline/orchestrator;
- introduce speculative abstractions;
- perform broad refactors;
- clean unrelated style;
- implement deferred product ideas.

Fix demonstrated correctness and signal-quality issues only.

If second-pass inspection finds another issue that is **directly caused by the changes in PR #31**, fix it and report it.

If you find an unrelated pre-existing issue, document it separately rather than expanding scope — except for the explicitly included broken `architecture.md` link above.

---

# Final report

When finished, report:

1. exact fixes made;
2. any contract changes;
3. tests added or strengthened;
4. final Ruff / pytest / mypy results;
5. result of the repository's own `ai_doc check`;
6. whether pairwise observation outcome accounting is now complete;
7. whether `FindingAdapter` required code changes or only contract/test/documentation clarification;
8. final `STRUCTURE_NO_HEADINGS` heuristic and why it is conservative;
9. any directly adjacent PR #31 defect discovered during the second pass;
10. anything intentionally deferred.

Do not delete `task.md` yet.
