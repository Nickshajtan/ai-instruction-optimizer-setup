# PR #31 — Final Targeted Polish

Repository:

`Nickshajtan/ai-instruction-optimizer-setup`

Continue working on the existing PR #31 branch.

The second-pass hardening is accepted in principle. This is a **small targeted final polish**, not another general review.

Keep `task.md` for now.

There are exactly two areas to address:

1. remove the unnecessary coupling between `FindingAdapter` and `Analyzer`;
2. inspect and resolve the repository's own remaining `ai-doc check` warnings.

Do not touch the deferred gated pipeline work in this task.

---

# 1. Make `FindingAdapter` a clean first-class extension capability

The current implementation exposes:

```python
FindingAdapter
```

as a public protocol, but operationally discovers adapters only among objects registered through:

```python
registry.add_analyzer(...)
```

This forces a pure adapter to pretend to be an analyzer:

```python
def analyze(...):
    return []
```

That is conceptually awkward and makes the public API less useful than it could be.

The desired model is simple:

```text
Analyzer
    └── produces findings

FindingAdapter
    └── transforms the produced finding set
```

An extension object may implement either capability or both.

## Required change

Add the **smallest clean registration mechanism** necessary for project extensions to register a finding adapter directly.

Conceptually:

```python
registry.add_finding_adapter(adapter)
```

or an equivalently small API consistent with the existing registry naming conventions.

Do not build a generic middleware framework.

Do not introduce priorities, dependency graphs, events, hooks, phases, dynamic dispatch infrastructure, or a generic capability registry.

The registry only needs to retain an ordered collection of finding adapters.

---

## Production behavior

Static analysis should conceptually remain:

```text
built-in analyzers
        ↓
extension analyzers
        ↓
complete finding set
        ↓
finding adapters in deterministic registration order
        ↓
sort/report
```

An extension object that only adapts findings must not need to implement:

```python
analyze(...)
```

An extension object may still implement both `Analyzer` and `FindingAdapter` if that is useful.

Preserve deterministic composition.

For adapters:

```text
A
↓
B
↓
C
```

the output of A becomes the input of B, then C.

Do not silently deduplicate or reorder adapters.

---

## Backward compatibility

Existing project extensions written using the PR #31 form:

```python
class ProjectAdapter:
    def analyze(...):
        return []

    def adapt_findings(...):
        ...

registry.add_analyzer(ProjectAdapter())
```

should continue to work if preserving that behavior is cheap and does not make the contract ambiguous.

Prefer backward compatibility because this API already exists on the PR branch and tests/documentation may rely on it.

However, establish one canonical documented registration mechanism for pure adapters.

Avoid executing the same adapter twice if an object is registered through both mechanisms.

Use the smallest deterministic rule necessary.

---

## Public API

`FindingAdapter` must remain available through:

```python
ai_doc.api.v1
```

If project extension authors need a registry type or helper to use the new registration method, expose only what the existing extension API convention requires.

Do not expose internal implementation classes unnecessarily.

---

## Documentation

Update the extension guide so a pure project-specific adapter can look approximately like:

```python
from ai_doc.api.v1 import AnalysisContext, Finding, FindingAdapter


class ProjectClarityAdapter(FindingAdapter):
    reference_sections = {"Architecture", "Project Context"}

    def adapt_findings(
        self,
        context: AnalysisContext,
        findings: list[Finding],
    ) -> list[Finding]:
        return [
            finding
            for finding in findings
            if not (
                finding.code == "CLARITY_NO_ACTIONABLE_CONTENT"
                and finding.section in self.reference_sections
            )
        ]


def register(registry) -> None:
    registry.add_finding_adapter(ProjectClarityAdapter())
```

No dummy `analyze()` should be required.

Clearly document:

- analyzers produce findings;
- adapters transform the resulting finding collection;
- adapters run after analyzers;
- adapters compose in registration order;
- project-specific policy belongs here rather than in core heuristics when appropriate.

---

## Required tests

At minimum prove:

### A. Pure adapter

A class implementing only:

```python
adapt_findings(...)
```

can be registered and affects the real CLI production path.

### B. No dummy analyzer

The pure adapter does not need `analyze()`.

### C. Analyzer preservation

Built-in and unrelated extension analyzers still run normally.

### D. Multiple adapters

Two adapters compose deterministically in registration order.

### E. Combined capability

An object implementing both analyzer and adapter behaves predictably.

### F. No duplicate execution

If backward-compatible analyzer-based adapter discovery remains supported, ensure the same adapter is not accidentally applied twice.

### G. Public API

The project extension fixture uses only supported public extension imports/contracts.

---

# 2. Make the repository self-check clean

The previous report states:

```text
python -m ai_doc check . --format json --non-interactive
```

now passes without integrity failure but still produces analyzer warnings.

Do not stop at:

> passed with analyzer warnings only

This repository is the primary dogfooding target for `ai-doc`.

Its own documentation should ideally be a **clean reference fixture** for the analyzer.

Run:

```bash
python -m ai_doc check . --format json --non-interactive
```

and inspect **every remaining finding**.

Classify each finding before changing anything:

```text
finding
├── real documentation problem
├── analyzer false positive / poor signal
└── intentional condition that should remain reported
```

Do not mechanically edit documentation merely to silence the tool.

---

## 2.1 Real documentation problems

If a finding identifies a genuine local documentation defect, fix the documentation.

Examples may include:

- stale links;
- unnecessary duplication;
- genuinely orphaned instruction docs;
- confusing structure;
- missing routing;
- actionable instruction sections that are accidentally non-actionable;
- other concrete defects.

Preserve meaning while fixing them.

Do not rewrite large documents solely to satisfy heuristics.

---

## 2.2 False positives

If a remaining warning is clearly a false positive in the repository and reveals a **generic core heuristic defect**, fix the smallest underlying analyzer issue.

Requirements:

- reproduce it with a focused regression test;
- make the correction generic;
- preserve legitimate positive cases;
- prefer fewer false positives over higher finding counts;
- do not hard-code this repository's filenames/headings unless they represent an established generic convention.

This is dogfooding: a false positive found here is useful product evidence.

---

## 2.3 Intentional findings

If a finding represents a genuinely intentional condition that the analyzer is correctly reporting, do not corrupt documentation or weaken the analyzer merely to obtain zero findings.

Instead:

1. explain why the finding is legitimate;
2. determine whether the existing supported configuration/extension mechanisms can express the repository's intent;
3. use those mechanisms if appropriate.

Do not invent a suppression framework solely for this cleanup.

---

# 3. Desired self-check result

The target is:

```text
ai-doc check .
        ↓
0 unexplained findings
```

Preferably:

```text
0 findings
```

But do **not** game the analyzer to achieve zero.

If any finding intentionally remains, the final report must list it individually and explain why retaining it is more correct than suppressing or fixing it.

The important invariant is:

> every self-check finding is either fixed or consciously justified.

---

# 4. Re-run regression validation

After these changes run:

```bash
python -m ruff check .
python -m pytest
python -m mypy
python -m ai_doc check . --format json --non-interactive
```

Report the exact self-check finding count before and after this polish.

For any analyzer behavior changed because of dogfooding, report:

```text
observed finding
→ why it was wrong
→ generic correction
→ regression test
→ legitimate positive behavior preserved
```

---

# 5. Scope boundaries

Do not implement the deferred gated evidence pipeline.

Do not redesign:

- analyzer execution;
- extension loading;
- optimizer search;
- observations;
- provider abstractions;
- configuration inheritance;
- reporting;
- CLI lifecycle.

Do not introduce:

- generic middleware;
- hook/event systems;
- adapter priorities;
- dependency injection redesign;
- suppression DSL;
- rule engine;
- execution DAG;
- pipeline framework.

The `FindingAdapter` change should remain a small registry capability.

The self-check cleanup should remain evidence-driven dogfooding.

If either task unexpectedly requires substantial architecture, stop that part and explain why instead of expanding scope.

---

# Final report

Report:

1. `FindingAdapter` registration API after the change;
2. backward-compatibility behavior;
3. deterministic adapter composition semantics;
4. every self-check finding observed before the fixes;
5. disposition of each finding;
6. any generic analyzer correction made because of dogfooding;
7. self-check finding count before and after;
8. Ruff result;
9. pytest result;
10. mypy result;
11. final `ai-doc check` result;
12. anything intentionally left unchanged.

Do not delete `task.md`.

Do not implement the gated pipeline yet.
