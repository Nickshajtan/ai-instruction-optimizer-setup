# ai-doc — Release-Closing Specification

## Context

`ai-doc` is already a substantial repository-level quality and evidence layer for AI-facing documentation.

It currently provides:

- deterministic static analysis;
- documentation discovery and profiles;
- structure, clarity, duplication, contradiction, and FinOps/context analysis;
- token/context budgets;
- optional local semantic ML;
- Promptfoo and DeepEval integrations;
- semantic optimization;
- pairwise predictive evaluation;
- provider-neutral semantic execution;
- request/token/USD budgets in optimization paths;
- observability;
- C1 planning probes;
- C2 isolated execution probes;
- CLI/API/configuration contracts;
- packaging and executable distribution.

The project does **not** need a new architecture, benchmark framework, evaluation research program, dashboard, harness integration, or additional evidence tier.

This task is deliberately a **release-closing cleanup**.

After this work, `ai-doc` should be considered ready for real-world dogfooding and release.

---

# Goal

Close the remaining two functional gaps and align product documentation with what the tool actually is.

The final product positioning is:

> `ai-doc` is a quality, evidence, and cost gateway for AI-facing repository documentation.

It should:

1. detect cheap deterministic defects and risk signals;
2. model repository documentation/context structure;
3. escalate to external evaluation only when requested;
4. delegate actual LLM evaluation to mature engines such as Promptfoo and DeepEval;
5. enforce explicit cost/request/token limits for external evaluation;
6. normalize evidence without claiming that static heuristics prove real-agent failure.

Do **not** attempt to prove that optimized Markdown is universally better for LLMs.

Do **not** add C3 statistical benchmarking.

---

# Scope

Implement only these three areas:

1. Improve the Promptfoo adapter so Promptfoo can operate as a full evaluation backend rather than only an `echo + contains/not-contains` lexical checker.
2. Apply budget enforcement consistently to external evaluation, especially `ai-doc check --deep`.
3. Rewrite the README/product documentation around the correct product model.

Anything beyond this is out of scope unless strictly necessary to preserve existing behavior.

---

# 1. Promptfoo Adapter — Full Backend Support

## Current problem

The existing `PromptfooEvaluator` is intentionally lexical.

It currently uses approximately:

```text
provider: echo
assert:
  contains
  not-contains
```

This is useful as a cheap deterministic adapter, but it does not expose Promptfoo as the richer evaluation framework that the product expects it to be.

The adapter should not reimplement Promptfoo.

`ai-doc` should translate its domain-level evaluation scenarios into Promptfoo configuration and let Promptfoo perform evaluation.

---

## Design principle

The stable domain contract remains:

```yaml
id: validation
profile: coding-task
task: |
  Fix the failing unit test.

expected:
  required:
    - run relevant validation
  forbidden:
    - modify generated files
```

Users should not need to write raw Promptfoo YAML for ordinary `ai-doc` usage.

`ai-doc` owns:

- scenario discovery;
- repository/context composition;
- domain-level expected behavior;
- configuration;
- budget policy;
- evidence normalization.

Promptfoo owns:

- assertion execution;
- model-backed grading;
- Promptfoo-specific evaluation behavior.

---

## Required behavior

Extend Promptfoo configuration so `ai-doc` supports at least two modes.

### Lexical mode

Preserve the existing cheap behavior.

Equivalent to:

```yaml
assert:
  - type: contains
  - type: not-contains
```

This must remain available because it is cheap, deterministic, and useful.

Do not remove or silently change existing lexical behavior.

---

### Model-graded mode

Allow Promptfoo to use model-backed assertions for semantic evaluation.

Support a small explicit abstraction over Promptfoo rather than exposing every Promptfoo feature.

A suitable configuration may look conceptually like:

```yaml
evaluation:
  deep:
    engine: promptfoo
    mode: model_graded
    model: some-explicit-model
    assertion: g-eval
```

Exact naming may differ if the existing configuration model suggests something cleaner.

At minimum support one mature Promptfoo semantic assertion mechanism such as:

```text
g-eval
```

or:

```text
llm-rubric
```

Prefer the option that maps most naturally to `EvaluationScenario`.

Do not implement five different model-graded strategies just because Promptfoo supports them.

One good production path is enough.

---

## Scenario mapping

Required and forbidden behaviors should be converted into an explicit evaluation rubric.

Example source:

```yaml
expected:
  required:
    - run tests
    - preserve public API
  forbidden:
    - edit generated files
```

Promptfoo evaluation should judge whether the evaluated documentation/context supports those requirements.

The adapter must clearly distinguish:

```text
lexical assertion
```

from:

```text
semantic/model-graded assertion
```

in normalized results.

---

## Explicit models

No implicit provider/model defaults.

If semantic Promptfoo evaluation requires a model, it must be explicitly configured.

Do not silently select OpenAI or any other provider/model.

Failure should be a concise configuration error.

This should follow the same philosophy already used for DeepEval.

---

## Result normalization

Continue returning the internal `EvaluationResult`.

Preserve:

```text
engine
passed
cases
score
message/reason
raw_summary
```

where available.

Add enough metadata to distinguish evaluation type, for example:

```json
{
  "semantic": true,
  "backend": "promptfoo",
  "mode": "model_graded"
}
```

Lexical Promptfoo results should continue to report:

```json
{
  "semantic": false
}
```

Do not leak Promptfoo's entire raw schema into the stable public API.

---

## Compatibility

Existing configuration using:

```yaml
engine: promptfoo
```

must continue working.

Choose a compatibility-safe default.

Prefer preserving lexical mode as the default unless current documented behavior clearly requires otherwise.

Semantic/model-graded Promptfoo evaluation should be explicit.

---

# 2. Unified External Evaluation Budget Enforcement

## Current problem

Optimization/provider-backed semantic work already supports limits such as:

```text
max_llm_requests
max_input_tokens
max_output_tokens
max_cost_usd
```

through `BudgetedSemanticProvider` and search-controller accounting.

However, direct deep evaluation such as:

```bash
ai-doc check . --deep
```

can call evaluators such as DeepEval directly without equivalent enforcement.

This violates the desired product invariant:

> External evaluation must respect declared request/token/cost budgets.

---

## Goal

Introduce a consistent evaluation-budget boundary for external evaluation paths.

The implementation should reuse existing abstractions wherever possible.

Do not build a second independent FinOps system.

---

## Budget model

The effective budget should be able to constrain:

```text
requests
input tokens
output tokens
USD cost
```

Conceptually:

```yaml
evaluation:
  deep:
    engine: deepeval
    model: ...
    budget:
      max_requests: 10
      max_input_tokens: 50000
      max_output_tokens: 10000
      max_cost_usd: 0.50
```

Exact placement may differ if reusing existing `SearchConfig` or a shared budget object produces a cleaner model.

The important requirement is semantic consistency, not exact YAML syntax.

---

## Hard invariant

For external evaluation:

```text
No new external evaluation request may start once the known accumulated usage has reached or exceeded the configured limit.
```

If one request crosses a limit because actual usage is only known after completion:

1. preserve and record the actual usage;
2. do not discard the result;
3. block subsequent external calls;
4. report that the budget was exhausted or exceeded.

This should be consistent with the existing `BudgetedSemanticProvider` semantics.

---

## Usage accounting

Define a common evaluator usage contract.

Prefer reusing:

```python
ProviderUsage
```

or extracting a small common usage model rather than creating competing structures.

External evaluators should expose reported or measurable usage where available:

```text
requests
input_tokens
output_tokens
cost_usd
cost_source
cache_hits
```

Unknown values must remain unknown or clearly marked.

Do not invent token or cost values.

---

## Backend limitations

Promptfoo and DeepEval may not expose usage identically.

Handle this honestly.

If an evaluator cannot report an exact value:

- do not fabricate it;
- mark that dimension as unknown;
- enforce dimensions that are known;
- document the limitation.

For USD enforcement specifically, distinguish between:

```text
provider-reported cost
estimated cost
unknown cost
```

Do not claim a hard USD cap if the backend provides no way to determine cost before or after calls.

If hard enforcement is impossible for a backend, fail closed only when the user explicitly requires that dimension as strict and the implementation cannot enforce it reliably.

Otherwise expose the limitation.

Use judgment and keep the behavior predictable.

---

## `check --deep`

`ai-doc check --deep` must pass through the budget-aware evaluation path.

Budget exhaustion should produce:

- stable machine-readable evidence;
- concise CLI output;
- a documented exit code.

Do not treat budget exhaustion as a Python traceback/internal crash.

Reuse existing exit-code semantics where sensible.

Do not introduce a new exit code unless necessary.

---

## Optimization

Do not regress the existing optimization budget behavior.

The current tests for:

```text
request exhaustion
token exhaustion
cost exhaustion
one-call overrun
preventing later external work
```

must remain valid.

Where possible, make `check --deep` and optimizer evaluation share infrastructure.

---

# 3. README And Product Positioning

The README currently overemphasizes “improving Markdown.”

Rewrite the opening sections around the actual system.

---

## Required positioning

Use language equivalent to:

> `ai-doc` is a quality, evidence, and cost gateway for AI-facing repository documentation.

Explain that AI-facing documentation includes:

- `AGENTS.md`;
- `CLAUDE.md`;
- `GEMINI.md`;
- agent skills;
- Copilot instructions;
- Cursor rules;
- architecture/reference docs;
- project-specific Markdown.

---

## Explicit non-claim

The README must clearly state:

> Static findings do not prove that an LLM or agent will fail.

Different evidence tiers answer different questions.

For example:

```text
A0 deterministic/static
    → verifies structural facts and policy violations

A1 local semantic
    → detects probabilistic local semantic signals

B predictive evaluator
    → predicts likely semantic quality/behavior

C1 planning probe
    → observes real target planning behavior

C2 execution probe
    → observes real target execution behavior
```

Preserve the evidence pyramid.

Make it central to the product explanation.

---

## Explain linting correctly

The README should explain that linting catches two categories.

### Hard/verifiable defects

Examples:

- broken references;
- invalid configuration;
- missing required structures;
- budget violations;
- deterministic duplication;
- invalid document relationships.

These are suitable for blocking CI when configured.

### Risk signals

Examples:

- clarity concerns;
- possible semantic duplication;
- possible contradiction;
- excessive context;
- weak hierarchy.

These are not proof that an agent will fail.

They are signals that may justify review or escalation to stronger evidence.

Avoid describing every warning as an “error.”

---

## Explain why `ai-doc` exists above Promptfoo/DeepEval

Add a concise section such as:

### Why not use Promptfoo or DeepEval directly?

Explain:

Promptfoo and DeepEval are evaluation engines.

`ai-doc` adds repository/document-domain concerns:

- Markdown/document discovery;
- profiles and scope;
- context-loading model;
- documentation graph;
- static analysis;
- invariant preservation;
- context/token/FinOps analysis;
- evaluator-independent scenarios;
- budget/escalation policy;
- normalized results;
- real-agent probes.

Make clear that `ai-doc` delegates evaluation rather than replacing those frameworks.

Do not disparage Promptfoo or DeepEval.

---

## Explain when `ai-doc` is unnecessary

This is important.

Document that a project with:

```text
one small instruction file
few stable prompts
no multi-agent documentation structure
```

may be better served by direct Promptfoo/DeepEval usage or no additional tooling.

The value of `ai-doc` increases when AI-facing documentation becomes a system rather than a single prompt.

---

## Promptfoo documentation

Update the README/configuration docs to accurately distinguish:

```text
Promptfoo lexical mode
```

and:

```text
Promptfoo model-graded mode
```

Do not imply that the existing lexical adapter is semantic evidence.

---

# 4. Tests

Add focused regression coverage.

Do not build benchmark suites.

---

## Promptfoo tests

Cover:

1. existing lexical configuration remains compatible;
2. lexical mode generates `echo + contains/not-contains`;
3. model-graded mode generates the expected Promptfoo semantic assertion;
4. semantic Promptfoo requires explicit model/provider configuration where applicable;
5. normalized results correctly report semantic vs non-semantic evidence;
6. invalid Promptfoo configuration fails cleanly.

Use fake runners/config inspection.

Do not require live paid models in normal CI.

---

## Budget tests

Cover at least:

1. `check --deep` stops additional requests after request budget exhaustion;
2. input-token budget;
3. output-token budget;
4. USD budget;
5. one completed call that crosses a limit is recorded before further work is stopped;
6. unknown usage is represented honestly;
7. optimizer budget behavior remains unchanged;
8. observation logging records budget-relevant usage where available.

Tests must remain deterministic.

---

# 5. Documentation And Stable API

Update as necessary:

```text
README.md
docs/guides/configuration.md
docs/design/predictive-evaluation.md
docs/guides/semantic-optimization.md
docs/operations/release-notes.md
```

Update public JSON/config schemas only when required by the implementation.

Do not casually expand `ai_doc.api.v1`.

If a new reusable usage/budget type becomes part of the stable API, justify it explicitly.

Prefer internal implementation unless downstream extensions genuinely need it.

---

# 6. Release Notes

Prepare the next patch/minor release notes.

Choose version according to compatibility impact.

A patch release is appropriate if:

- existing config continues working;
- Promptfoo lexical behavior remains default;
- new semantic/budget configuration is additive.

Use a minor release if existing public semantics change materially.

Do not bump version unnecessarily.

---

# Explicit Non-Goals

Do NOT:

- build statistical C3 benchmarks;
- prove that optimized Markdown improves all LLMs;
- create a universal “prompt quality score”;
- add dashboard/UI;
- add OpenRouter/model routing;
- add a general harness;
- create a new plugin framework;
- redesign the extension system;
- build generic experiment tracking;
- reimplement Promptfoo features;
- reimplement DeepEval metrics;
- add arbitrary evaluator engines;
- introduce new agent runtimes;
- redesign C1/C2 probes;
- rewrite the optimizer;
- expand GEPA;
- perform unrelated refactors.

If an unrelated cleanup is attractive but not necessary, leave it alone.

---

# Definition of Done

The task is complete when all of the following are true:

- Existing Promptfoo lexical evaluation still works.
- Promptfoo can also run at least one real model-graded semantic evaluation mode through `ai-doc`.
- Promptfoo remains a backend rather than being reimplemented.
- DeepEval continues to work.
- `check --deep` participates in external-evaluation budget enforcement.
- request, token, and cost usage are tracked/enforced to the extent the backend can reliably expose them.
- budget exhaustion prevents subsequent paid/external work.
- usage from a call that crosses a budget is preserved.
- existing optimizer FinOps behavior does not regress.
- README clearly positions `ai-doc` as a quality/evidence/cost gateway.
- README explicitly states that lint warnings do not automatically prove agent failure.
- README explains Promptfoo/DeepEval vs `ai-doc`.
- README explains when `ai-doc` is overkill.
- documentation accurately distinguishes lexical, predictive, and observed evidence.
- no C3 benchmark system is added.
- unit/integration/security tests pass.
- Ruff, Pylint, MyPy, and existing quality checks pass.
- deterministic CI remains green.
- release notes are updated.
- no unrelated architecture changes are introduced.

---

# Final Review Requirement

Before finishing, review the diff specifically for scope creep.

Answer these questions:

1. Did this task make Promptfoo a better backend rather than duplicating it?
2. Is external evaluation now consistently budget-aware?
3. Are unknown cost/token values represented honestly?
4. Does the README distinguish facts, risk signals, predictions, and observed agent behavior?
5. Did we avoid turning this into another benchmark/research project?
6. Could `ai-doc` now reasonably be released and dogfooded without another major implementation milestone?

If the answer to #6 is no, identify only concrete release-blocking defects.

Do not propose speculative next-product features.

The intended outcome of this task is:

> fix the two remaining product gaps, correct the product story, release it, and stop feature development until real usage produces evidence for the next change.