# ai-doc — Post-Integration Core Hardening Specification

## Target

Repository:

`Nickshajtan/ai-instruction-optimizer-setup`

This specification applies to the `ai-doc` core only.

The findings addressed by this specification were discovered during the first real downstream integration and dogfooding of `ai-doc` against a production-scale repository containing multiple AI-documentation conventions, including `.ai/`, `.claude/`, `.codex/`, and `.github/` instruction and skill files.

The purpose of this work is **not** another general architecture or cleanup pass.

The purpose is to correct concrete correctness and signal-quality problems exposed by real usage while preserving the architecture and contracts already established in `ai-doc`.

Before editing, verify every referenced behavior against the current repository state. Source locations mentioned in the findings are navigation aids, not authoritative line numbers.

---

## Scope

### In scope

Only narrowly scoped changes that address the integration findings explicitly described in this specification:

- correctness problems where `ai-doc` can produce or imply a misleading result;
- discovery problems caused by the tool's own runtime artifacts;
- analyzer false positives or excessive noise demonstrated by real repository usage;
- small diagnostics or machine-readable state required to make execution semantics truthful;
- focused regression tests for every behavioral change.

### Out of scope

Do not use this work as an opportunity to:

- redesign the optimizer or search architecture;
- redesign the extension system or its contracts;
- redesign configuration inheritance or nested configuration semantics;
- add new provider abstractions;
- redesign observability;
- redesign the evidence pyramid;
- add orchestration or cross-tool pipeline contracts;
- introduce a FinOps service or workflow-level budgeting system;
- perform broad dead-code cleanup;
- perform style-only refactoring;
- introduce abstractions solely for hypothetical future consumers;
- modify downstream/company-specific integration code.

Downstream adapters, wrappers, configuration overlays, vendoring layout, and repository-specific documentation remain consumer concerns unless a finding below explicitly demonstrates that the responsibility belongs in `ai-doc` core.

---

## Engineering Principles

### 1. Fix observed behavior, not hypothetical architecture

Every change in this specification originates from behavior observed during real integration.

Prefer the smallest correction that fixes the demonstrated problem.

Do not generalize a local finding into a new framework, abstraction layer, configuration hierarchy, or extension point unless the existing domain model cannot express the required semantics.

### 2. Preserve existing concepts before creating new ones

Before adding a new field, enum, profile, mode, toggle, or abstraction, inspect the existing domain model and configuration for a concept that already represents the same semantics.

In particular, reuse existing document profiles, loading semantics, extension contracts, runtime state, and reporting models where they already provide the appropriate boundary.

Do not create two concepts that mean substantially the same thing.

### 3. Deterministic-by-default remains invariant

No change in this specification may introduce an LLM, semantic-provider, network, or other paid/external call on a path that does not already perform one.

`conservative` mode must remain zero-spend.

Optional semantic evaluation must remain explicitly requested or configured.

### 4. Fail closed

Do not introduce:

- implicit provider selection;
- implicit model selection;
- silent network access;
- silent fallback from an unavailable configured capability to a materially different capability;
- a success-looking result when a requested evaluation did not actually execute.

Unavailable evidence and successful evidence are different states and must remain distinguishable.

### 5. Prefer epistemic honesty over reassuring output

`ai-doc` must not imply that something was evaluated, judged, verified, or passed when the corresponding evaluation did not occur.

When the tool lacks evidence, report the absence of evidence rather than manufacturing a positive conclusion.

Machine-readable artifacts and human-readable output must agree about what actually happened.

### 6. Preserve privacy guarantees

Observability and reporting changes must not begin recording raw document contents, prompts, model responses, secrets, environment values, API keys, or unnecessary filesystem information.

Existing privacy-preserving identifiers and hashing behavior must remain intact.

### 7. Configuration remains strict

The configuration schema remains `extra="forbid"`.

Any genuinely necessary new configuration field must be represented explicitly in the Pydantic configuration model and documented.

Do not smuggle behavior through unknown YAML keys or ad-hoc dictionary access.

Do not silently change the existing explicit `--config` replacement semantics as part of an unrelated fix.

### 8. Core owns core-generated hazards

If `ai-doc` itself creates an artifact or runtime condition that can subsequently corrupt, contaminate, or misrepresent its own analysis, protecting against that hazard belongs in core where practical.

Consumers should not need to know undocumented internal cleanup rules merely to prevent the tool from analyzing its own scratch artifacts.

This principle does not justify absorbing consumer-specific policy into core.

### 9. Analyzer findings must optimize signal, not finding count

A technically detectable pattern is not automatically a useful finding.

Analyzer changes should preserve genuine defects while reducing demonstrated false positives, redundant findings, and high-volume low-information output.

Do not solve noisy heuristics by blindly suppressing an entire class of valid findings.

Prefer better classification, localization, aggregation, or use of existing document semantics.

### 10. Every behavioral fix requires regression evidence

Every behavioral change must include a focused automated test that:

1. reproduces the problematic behavior or semantic gap;
2. would fail against the previous implementation;
3. passes after the fix;
4. protects the intended behavior without unnecessarily freezing implementation details.

Where a fix distinguishes two cases, test both the corrected case and the case whose existing behavior must remain unchanged.

### 11. Preserve established contracts unless explicitly required

Existing public API, CLI, configuration, extension, process-wire, and output contracts should remain compatible unless a finding explicitly requires a contract change.

If a problem can be fixed through a diagnostic, additional machine-readable field, narrower analyzer rule, or internal invariant, prefer that over breaking existing behavior.

### 12. Stop when the demonstrated problems are fixed

Do not perform adjacent cleanup because the relevant files are already being edited.

Do not add speculative improvements discovered while implementing this specification.

If implementation exposes another plausible issue that is not necessary to satisfy an acceptance criterion below, report it separately rather than expanding the change.

The completion condition for this work is:

> the demonstrated integration problems are corrected, regression-tested, and the existing architecture remains stable.

It is **not**:

> the touched areas have been redesigned until no further improvement can be imagined.

---

## Existing Behavior That Must Not Regress

The current core already contains earlier hardening work. Preserve it, including:

- finite timeout behavior for command-based semantic-provider execution;
- DeepEval fail-closed behavior with no implicit OpenAI/model selection;
- provider-aware and explicitly qualified token-count semantics;
- input and output token pricing primitives;
- explicit missing `--config <path>` failure;
- operational semantic-provider failures not being silently converted into epistemic uncertainty;
- strict extension/process wire contracts;
- deterministic conservative execution;
- local append-only privacy-conscious observation logging.

Do not re-solve or redesign these areas unless required by one of the explicitly discussed findings below.

---

## Implementation Discipline

For each finding below:

1. verify the described behavior against current code before editing;
2. preserve the intent of the finding even if implementation details have moved;
3. implement the agreed correction and no broader redesign;
4. add focused regression coverage;
5. run the relevant test, lint, type/static-analysis, and repository quality gates;
6. report any material deviation from the specified solution rather than silently substituting a different design.

The priority labels below describe the impact of the observed problem. They are **not permission to broaden scope**.

## To implement

### P0-1 — Make Pairwise Semantic Execution Truthful and Enforceable

#### Problem

`optimize --pairwise-semantic` currently enables optional B-tier baseline-vs-candidate semantic judging, but it does **not** guarantee that any pairwise semantic comparison actually occurs.

Candidates may be rejected before reaching the pairwise stage because of deterministic/Tier-0 failures, duplication, budget limits, or other earlier gates.

A real downstream integration produced exactly this state:

- pairwise semantic judging was requested;
- zero candidates reached the pairwise stage;
- the semantic provider was never called for pairwise judging;
- the run still completed successfully;
- the resulting output could reasonably be interpreted as having passed semantic judgment.

This violates the project's epistemic-honesty principle:

> requested evidence is not the same as produced evidence.

The system must distinguish:

1. pairwise semantic judging was not requested;
2. pairwise semantic judging was requested but never performed;
3. pairwise semantic judging was requested and one or more comparisons were actually performed.

---

#### Required behavior

##### 1. Make pairwise execution state first-class

Add explicit typed execution state to `OptimizationRun`:

```python
pairwise_semantic_requested: bool = False
pairwise_comparisons_performed: int = 0
```

Equivalent naming is acceptable only if it preserves the same precise semantics.

Do **not** replace these with a generic field such as:

```python
semantic_evaluations
```

`ai-doc` has multiple semantic operations with different meanings:

- deep scenario evaluation;
- pairwise candidate comparison;
- semantic generation;
- invariant discovery/verification;
- prompt suboptimization.

This task concerns pairwise B-tier judgment specifically.

`pairwise_comparisons_performed` must count comparisons that actually reached the pairwise evaluator. It must not count candidates that merely could have been compared or semantic calls made for unrelated purposes.

Because `OptimizationRun` is serialized into the existing run/report artifacts, this state must become available in the machine-readable output without introducing a parallel reporting model.

The resulting artifacts must be able to distinguish at least:

```text
requested=false, performed=0
    → pairwise semantic judging was not requested

requested=true, performed=0
    → pairwise semantic judging was requested but NOT JUDGED

requested=true, performed>0
    → pairwise semantic judging actually occurred
```

---

##### 2. Preserve normal `--pairwise-semantic` execution semantics

`--pairwise-semantic` remains an opt-in request to:

> run B-tier pairwise semantic judging for candidates that survive the preceding gates.

It must **not** mean that the baseline is independently judged or that every optimization run necessarily reaches the pairwise stage.

Update its CLI help text accordingly.

If `--pairwise-semantic` is requested but:

```text
pairwise_comparisons_performed == 0
```

the command must emit a prominent stderr diagnostic explaining that no pairwise semantic judgment occurred.

For example:

```text
Pairwise semantic judging was requested but not performed:
0 candidates reached the B-tier after earlier gates.
This run did NOT receive a pairwise semantic judgment.
```

Exact wording may differ, but it must be unmistakable that:

- semantic judging was requested;
- no pairwise comparison occurred;
- this is absence of semantic evidence, not a passing semantic result.

Without a strict requirement flag, preserve the command's existing exit semantics. Do not turn this condition into a failure by default.

---

##### 3. Add strict `--require-pairwise-semantic`

Add:

```text
--require-pairwise-semantic
```

This is a **postcondition**, not a new semantic evaluation mode.

Its contract is:

> the optimization run is only successful if at least one pairwise semantic comparison actually occurred.

`--require-pairwise-semantic` must imply `--pairwise-semantic`.

The user should therefore be able to write:

```bash
ai-doc optimize ... --require-pairwise-semantic
```

without also specifying:

```bash
--pairwise-semantic
```

When the strict flag is active:

```text
pairwise_comparisons_performed >= 1
    → continue with normal optimizer exit semantics

pairwise_comparisons_performed == 0
    → command must exit non-zero
```

The failure diagnostic must explain why the postcondition was not satisfied.

For example:

```text
Required pairwise semantic judging was not performed:
0 candidates reached the B-tier after earlier gates.
```

Use an exit code consistent with the CLI's existing exit-code conventions. Inspect the current taxonomy before introducing a new code; do not arbitrarily assign a new semantic meaning to an existing code.

---

##### 4. Keep `--deep` semantics separate

Do not redefine `--deep` as part of this task.

A deep semantic evaluation, semantic generation call, invariant operation, or prompt-suboptimizer call must **not** satisfy:

```text
--require-pairwise-semantic
```

Only an actual baseline-vs-candidate pairwise comparison satisfies the postcondition.

Do not introduce a generic `--require-semantic` policy framework as part of this change.

If broader semantic-evidence requirements become necessary later, they should be designed from real use cases rather than generalized from this one pairwise requirement.

---

#### Machine-readable output

Both existing optimization artifacts must expose the execution state through the serialized `OptimizationRun`:

```text
run.json
report.json
```

At minimum, downstream tooling must be able to determine:

```text
pairwise_semantic_requested
pairwise_comparisons_performed
```

Do not require downstream tooling to infer execution from:

- provider request counts;
- total cost;
- candidate count;
- presence of a configured provider;
- optimizer stop reason.

Those are not equivalent to proof that pairwise semantic judgment occurred.

---

#### Tests

Add focused regression coverage for at least the following cases.

**Case A — not requested**

```text
pairwise semantic disabled
→ requested == false
→ performed == 0
→ no "not judged" warning
→ existing exit behavior unchanged
```

**Case B — requested, but no candidate reaches B-tier**

```text
--pairwise-semantic
→ requested == true
→ performed == 0
→ loud NOT JUDGED diagnostic
→ existing non-strict exit behavior preserved
```

**Case C — requested and comparison occurs**

```text
--pairwise-semantic
→ candidate reaches pairwise evaluator
→ requested == true
→ performed >= 1
→ no "not judged" diagnostic
```

**Case D — strict requirement fails**

```text
--require-pairwise-semantic
→ no candidate reaches pairwise evaluator
→ requested == true
→ performed == 0
→ explicit diagnostic
→ non-zero exit
```

**Case E — strict requirement succeeds**

```text
--require-pairwise-semantic
→ at least one pairwise comparison occurs
→ requested == true
→ performed >= 1
→ pairwise postcondition itself does not cause failure
```

**Case F — unrelated semantic work does not satisfy the requirement**

Where practical using existing test infrastructure:

```text
semantic work occurs for another purpose
but pairwise comparison does not occur
→ pairwise_comparisons_performed == 0
→ --require-pairwise-semantic still fails
```

Do not make tests dependent on real external providers or network access.

---

#### Non-goals

Do not:

- change the optimizer gate order;
- force candidates through earlier gates merely to obtain semantic evidence;
- make `--pairwise-semantic` fail when zero comparisons occur unless the strict requirement is enabled;
- make the baseline undergo a new standalone semantic evaluation;
- redefine `--deep`;
- introduce generic semantic-evidence accounting;
- count unrelated semantic-provider calls as pairwise comparisons;
- redesign provider usage accounting;
- redesign the evidence pyramid;
- introduce new orchestration or pipeline abstractions.

The goal is narrowly:

> make the difference between **pairwise judging requested** and **pairwise judging actually performed** explicit, truthful, machine-readable, and optionally enforceable.

### P0-1A — Observe Pairwise Semantic Gate Behavior

#### Motivation

P0-1 makes the distinction between:

- pairwise semantic judging requested;
- pairwise semantic judging actually performed;

explicit and machine-readable.

The same production integration that exposed P0-1 also demonstrated that this execution boundary is valuable for future empirical analysis of the evidence pyramid.

We should collect the relevant machine facts now while the execution semantics are known, rather than attempting to reconstruct them later from logs, provider costs, or candidate artifacts.

This task extends the existing local observation mechanism with pairwise-semantic execution facts.

It does **not** add analytics, scoring, recommendations, dashboards, or interpretation.

The governing principle remains:

> **Record facts now. Derive interpretations later.**

---

#### Required behavior

##### 1. Record pairwise execution facts in optimization observations

Optimization observations must record the pairwise execution state introduced by P0-1.

At minimum, preserve:

```text
pairwise requested
pairwise comparisons performed
```

The observation must derive these values from the authoritative optimization run state.

Do not independently reconstruct whether pairwise judging occurred from:

- provider request counts;
- total model cost;
- candidate count;
- configured provider presence;
- CLI flags alone;
- optimizer stop reason.

The `OptimizationRun` execution facts introduced by P0-1 are authoritative.

---

##### 2. Record pairwise outcomes

When pairwise comparisons actually occur, record aggregate outcome counts sufficient for later offline analysis.

At minimum distinguish:

```text
candidate preferred
baseline preferred
uncertain
```

For example, the conceptual observation shape may be:

```json
{
  "pairwise": {
    "requested": true,
    "comparisons_performed": 4,
    "candidate_preferred": 1,
    "baseline_preferred": 2,
    "uncertain": 1
  }
}
```

Exact DTO organization may follow the existing observability model, but the semantics must remain explicit.

The following invariant must hold:

```text
candidate_preferred
+ baseline_preferred
+ uncertain
== pairwise_comparisons_performed
```

if the existing pairwise result model has exactly these exhaustive terminal outcomes.

Before enforcing this invariant, inspect the actual `PairwiseSemanticResult` model. If additional legitimate outcomes exist, represent them truthfully rather than forcing them into one of these three categories.

Do not discard or misclassify existing domain states merely to obtain a convenient telemetry schema.

---

##### 3. Capture pre-pairwise rejection/gate facts only where already available

Where the existing optimizer state already provides reliable structured information explaining why candidates did not reach pairwise judging, expose useful aggregate counts in the observation.

Examples may include candidates stopped or rejected because of:

- deterministic/Tier-0 constraints;
- duplicate candidate detection;
- budget exhaustion;
- other existing structured rejection/stop reasons.

However:

> do not create a second rejection taxonomy solely for observability.

Reuse existing structured domain state, rejection reasons, or stop reasons where their semantics are sufficiently stable and unambiguous.

If the current state cannot reliably distinguish a particular reason without redesigning search execution, omit that metric for now.

Missing telemetry is preferable to invented telemetry.

Do not parse human-readable error/rejection strings into a new pseudo-structured taxonomy unless those strings are already established stable identifiers.

---

#### Observation semantics

The observation layer records execution facts, not conclusions.

For example:

```text
requested=true
comparisons_performed=0
```

is a fact.

The observation layer must **not** turn it into interpretations such as:

```text
B-tier ineffective
semantic tier unnecessary
cheap gates too aggressive
optimization failed
```

Likewise:

```text
candidate_preferred=1
baseline_preferred=9
```

must not automatically produce a recommendation to remove or reorder the semantic tier.

Those interpretations belong to later offline analysis across a meaningful number of real runs.

---

#### Future analysis enabled by this data

Do not implement these metrics in this task.

The collected facts should merely make later offline analysis possible, including questions such as:

```text
How often does pairwise B-tier judging actually execute?

Why do candidates fail to reach it?

How often does pairwise judging prefer a candidate?

How often does it preserve the baseline?

How often is it uncertain?

What is the marginal cost of obtaining a decisive pairwise result?

Does B-tier provide enough additional information to justify
its current position and cost in the evidence pyramid?
```

These are examples of future analysis goals, not runtime behavior.

Do not add derived fields for them now.

---

#### Privacy

Preserve the existing observation privacy guarantees.

Do not record:

- document bodies;
- candidate bodies;
- prompts;
- semantic-provider responses;
- raw filesystem paths;
- secrets;
- environment values;
- API keys.

Prefer aggregate counts and existing privacy-safe identifiers.

No additional content-level telemetry is required for this task.

---

#### Failure semantics

Observation logging remains non-critical infrastructure.

Failure to write the new pairwise observation data must follow the existing observation failure behavior and must not change the primary optimization result.

In particular:

```text
observation write failure
≠
optimization failure
```

The strict behavior introduced by:

```text
--require-pairwise-semantic
```

depends on the authoritative optimization execution state, **not** on successful observation persistence.

Telemetry must never become the mechanism enforcing P0-1.

---

#### Tests

Add focused tests covering at least:

**Case A — pairwise not requested**

```text
requested == false
comparisons_performed == 0
outcome counts == 0
```

**Case B — pairwise requested but never reached**

```text
requested == true
comparisons_performed == 0
outcome counts == 0
```

**Case C — pairwise comparisons occur**

Verify that:

```text
requested == true
comparisons_performed > 0
```

and the observed outcome counts match the actual pairwise results.

**Case D — uncertain result**

An actual `UNCERTAIN` pairwise result must be recorded as uncertain and must not be silently classified as either candidate-preferred or baseline-preferred.

**Case E — observation write failure**

Existing non-fatal observation failure semantics remain unchanged.

Tests must not require a real external provider or network access.

---

#### Non-goals

Do not:

- build an analytics subsystem;
- add pandas analysis to core;
- add a database;
- add SQLite;
- add remote telemetry;
- add OpenTelemetry;
- add dashboards;
- calculate evidence-tier ROI at runtime;
- calculate pairwise usefulness scores;
- automatically reorder the evidence pyramid;
- add human feedback collection;
- add LLM-based telemetry interpretation;
- redesign optimizer rejection reasons solely for telemetry;
- introduce a generic event bus;
- redesign the observation schema beyond what is necessary to represent these facts.

The goal is narrowly:

> preserve enough truthful machine-observed data from real pairwise execution to support evidence-based analysis of B-tier behavior after sufficient dogfooding runs have accumulated.

### P0-2 — Make Explicit-Config Observability Behavior Visible

#### Problem

An explicit configuration passed through:

```bash
ai-doc ... --config <path>
```

is a complete replacement configuration.

It does not inherit omitted fields from the repository-root `.ai-doc.yaml`.

This behavior is intentional and must remain unchanged.

However, `observability.enabled` defaults to `false`. Therefore an explicit scoped configuration that omits the `observability` block silently disables observation logging for that run.

This was observed during real downstream integration: several scoped configurations executed successfully while producing no observation records because they did not repeat the root configuration's observability block.

The problem is **not** that explicit configuration uses replacement semantics.

The problem is that an important operational consequence of those semantics is currently silent:

> a user can believe that dogfooding/telemetry data is being collected while the explicit configuration has disabled it.

This is especially important now that optimization execution facts such as pairwise semantic reach and outcomes are intentionally being collected for later empirical analysis.

---

#### Required behavior

##### 1. Preserve explicit-config replacement semantics

Do not change the meaning of:

```bash
--config <path>
```

An explicit configuration remains self-contained.

Do not:

- merge the repository-root `.ai-doc.yaml` into it;
- inherit `observability` from the root config;
- introduce general config inheritance;
- selectively inherit arbitrary omitted fields;
- silently change replacement semantics into merge semantics.

The following remains valid:

```text
root .ai-doc.yaml
        +
--config scoped.yaml
        ↓
scoped.yaml is the effective explicit configuration
```

not:

```text
root .ai-doc.yaml
        +
scoped.yaml
        ↓
implicit merged configuration
```

---

##### 2. Warn when explicit configuration results in disabled observability

When configuration is supplied explicitly through:

```bash
--config <path>
```

and the resulting effective configuration has:

```text
observability.enabled == false
```

emit one concise warning to stderr.

For example:

```text
Observability is disabled for this run —
no observations will be written (config: <path>).
```

Exact wording may differ, but the warning must clearly communicate:

1. observability is disabled;
2. no observation records will be produced;
3. the behavior applies to the current run;
4. which explicit configuration produced the effective state.

This is an informational operational warning.

It must not change the command's exit code.

---

##### 3. Warn based on effective behavior, not merely field presence

The diagnostic must reflect the resulting configuration semantics.

For example:

```yaml
observability:
  enabled: false
```

must warn.

A config that simply omits:

```yaml
observability:
```

also results in `enabled == false` under the current model and must warn.

Conversely:

```yaml
observability:
  enabled: true
```

must not warn.

Do not implement the warning solely as:

```text
"observability" key missing from YAML
```

because explicit `enabled: false` has the same operational consequence.

The relevant fact is:

> observability is disabled in the effective explicit configuration.

---

##### 4. Keep implicit/default configuration behavior quiet

This warning is specifically about the operational footgun created by an **explicit replacement configuration**.

Do not emit the warning merely because observability is disabled in the normal implicit/default configuration.

For example:

```bash
ai-doc check .
```

with no `--config` and no observability enabled must retain its existing quiet behavior.

The distinction is intentional:

```text
implicit/default config + observability disabled
    → expected default behavior
    → no new warning

explicit --config + observability disabled
    → potentially surprising replacement consequence
    → warn
```

This avoids turning every default deterministic invocation into warning noise.

---

#### Implementation boundary

Prefer implementing this diagnostic at the CLI/config-loading boundary where both facts are known:

```text
an explicit config path was supplied
+
effective config has observability disabled
```

Do not change the generic observation writer to warn whenever observability is disabled.

The observation writer currently treats:

```text
observability.enabled == false
```

as a legitimate no-op state. Preserve that behavior.

Likewise, do not make `ConfigFileReader` responsible for user-facing warnings unless that is already the repository's established diagnostic boundary.

The warning belongs to execution/configuration UX, not to the persistence mechanism.

If several CLI commands currently duplicate explicit-config loading, use the smallest existing shared boundary that can provide consistent behavior without introducing a new configuration framework.

Avoid broad CLI refactoring solely to deduplicate one warning.

---

#### Relationship to observation data collection

This task does not make observability mandatory.

It makes the absence of observability visible when the user explicitly selects a configuration.

The resulting model remains:

```text
observability disabled intentionally
        ↓
valid execution
        ↓
no observation record
```

but for explicit configurations:

```text
observability disabled
        ↓
visible stderr warning
        ↓
valid execution
```

This preserves the existing opt-in observability contract while reducing accidental loss of dogfooding data.

---

#### Privacy and deterministic behavior

This change must not:

- enable telemetry automatically;
- introduce remote telemetry;
- make network calls;
- write additional observation data when observability is disabled;
- alter observation contents;
- alter observation privacy behavior;
- cause semantic-provider calls;
- affect deterministic/conservative execution.

It is a diagnostic-only behavior change.

---

#### Tests

Add focused regression coverage for at least the following cases.

**Case A — explicit config omits observability**

```text
--config scoped.yaml

scoped.yaml:
    no observability block

→ effective observability.enabled == false
→ one stderr warning
→ no observation file written
→ normal command exit semantics preserved
```

**Case B — explicit config explicitly disables observability**

```yaml
observability:
  enabled: false
```

Expected:

```text
→ one stderr warning
→ no observation file written
→ normal command exit semantics preserved
```

**Case C — explicit config enables observability**

```yaml
observability:
  enabled: true
```

Expected:

```text
→ no disabled-observability warning
→ existing observation behavior proceeds normally
```

**Case D — no explicit config**

```text
no --config
effective observability.enabled == false
```

Expected:

```text
→ no new warning
→ existing default behavior unchanged
```

Where practical, exercise the behavior through the CLI rather than testing only an internal helper, because the bug is specifically an execution/configuration UX problem.

---

#### Non-goals

Do not:

- default `observability.enabled` to `true`;
- make observability mandatory;
- merge root observability into explicit configurations;
- introduce config inheritance;
- introduce config composition/import syntax;
- change nested-config merge semantics;
- warn for every default run with observability disabled;
- turn disabled observability into a command failure;
- redesign observation storage;
- add remote telemetry;
- add analytics;
- change the observation schema as part of this task.

The goal is narrowly:

> preserve explicit-config replacement semantics while making accidental loss of observation data visible at execution time.

### P0-3 — Prevent Optimizer Scratch Output from Re-entering Source Discovery

#### Problem

`ai-doc optimize` writes generated candidates and related scratch artifacts under its optimization output root.

Those files are products of the optimization process. They are not source documentation.

However, source discovery currently relies on the effective configuration's `exclude` rules. The default configuration already excludes:

```text
.ai-doc-output/**
```

but an explicit `--config <path>` fully replaces the default configuration.

If that explicit configuration does not repeat the exclusion, a later optimization run can rediscover files previously generated under `.ai-doc-output/` and treat them as source Markdown.

This creates an invalid feedback loop:

```text
source documents
      ↓
   optimizer
      ↓
generated candidates / scratch output
      ↓
source discovery
      ↓
   optimizer
```

The optimizer can therefore begin optimizing its own generated artifacts as though they were project source documents.

This is a core correctness bug.

Protection against ingesting `ai-doc`'s own optimization artifacts must not depend solely on users remembering to reproduce a default exclusion in every explicit configuration.

---

#### Core invariant

Optimization artifacts generated by `ai-doc` for its own optimization process must not become optimization source documents merely because user configuration omitted an exclusion.

Conceptually:

```text
project Markdown
       ↓
optimization source discovery
       ↓
    optimizer
       ↓
tool-owned output root
       ↓
generated artifacts
       ✕
must not re-enter optimization source discovery
```

This is an ownership boundary:

> tool-owned optimization output is not optimization source input.

The core must enforce that boundary.

---

#### Required behavior

##### 1. Protect the default optimization output root independently of user excludes

The standard optimization output root:

```text
.ai-doc-output/
```

must not be rediscovered as source input by `ai-doc optimize`, even when the effective configuration does not contain:

```text
.ai-doc-output/**
```

For example, this explicit configuration:

```yaml
include:
  - "**/*.md"

exclude:
  - "vendor/**"
```

must not cause:

```text
.ai-doc-output/.../candidates/*.md
```

to become optimization source documents.

The existing default config exclusion may remain as defense in depth and for expected default discovery behavior.

However, correctness of optimization source discovery must not rely exclusively on that config entry.

---

##### 2. Treat this as an optimization ownership boundary, not a magical filename rule

Do not implement the fix as scattered path-name checks such as:

```python
if ".ai-doc-output" in str(path):
    ...
```

The semantic rule is not:

> directories named `.ai-doc-output` are inherently invalid Markdown.

The semantic rule is:

> the optimizer must not consume its own current/known tool-owned output as source input.

Prefer representing the protected output boundary at the narrowest existing layer responsible for optimization source discovery.

Generic Markdown discovery should remain conceptually separate from optimization-specific source protection where the current architecture permits that distinction.

---

##### 3. Preserve legitimate generic discovery behavior

Do not globally redefine every `.ai-doc-output/**` Markdown file as permanently undiscoverable through every API or command.

A user may intentionally inspect or analyze generated artifacts outside the optimization-source workflow.

Therefore, where compatible with the existing architecture:

```text
generic Markdown discovery
    → configured include/exclude semantics

optimization source discovery
    → configured include/exclude semantics
    + tool-owned optimization output protection
```

Do not broaden this task into a redesign of the generic discovery API.

---

##### 4. Protect custom `--output` roots where this can be done without lifecycle redesign

A custom output location is still tool-owned optimization output.

For example:

```bash
ai-doc optimize . --output tmp/optimizer-results
```

conceptually establishes:

```text
tmp/optimizer-results/**
```

as generated optimization state for that invocation/workflow, not source documentation.

The desired invariant therefore applies to both:

```text
default .ai-doc-output/
custom --output root
```

If the existing CLI/discovery lifecycle allows the effective output root to be supplied to optimization source discovery cleanly, protect the custom output root as well.

However, inspect the current execution order before changing it.

If custom-output protection would require material restructuring of:

- configuration loading;
- source discovery;
- optimization input construction;
- output-root lifecycle;
- command orchestration;

do **not** redesign those systems solely for this task.

In that case:

1. implement the default `.ai-doc-output/` hard protection now;
2. preserve all existing custom-output behavior;
3. explicitly report custom-output rediscovery protection as a remaining follow-up gap.

Do not silently claim full custom-output protection if only the default root is protected.

---

##### 5. User configuration may exclude more, but must not remove core protection

User-defined `exclude` rules remain additive from the perspective of source eligibility.

For optimization source discovery:

```text
eligible source
=
matches configured include
AND
does not match configured exclude
AND
is not protected tool-owned optimization output
```

A user may exclude additional paths.

An explicit configuration must not be able to accidentally remove the optimizer's protection against consuming its own scratch output merely by omitting `.ai-doc-output/**`.

This does not introduce general configuration inheritance.

It is a core runtime invariant outside the user-configurable exclusion set.

---

#### Relationship to explicit config replacement

Do not fix this bug by changing:

```text
--config <path>
```

from replacement semantics to merge/inheritance semantics.

P0-2 separately makes the operational consequences of explicit configuration more visible.

P0-3 must remain correct even under the existing replacement contract.

That is:

```text
explicit config omits default exclude
        ↓
default config is still replaced
        ↓
optimizer nevertheless protects its own output
```

The protection belongs to optimizer correctness, not config inheritance.

---

#### Recursive and repeated-run behavior

The fix must cover the real repeated-run failure mode.

For example:

```text
Run 1
source: docs/foo.md
output: .ai-doc-output/run-1/candidates/foo.md

Run 2
include: **/*.md
explicit config omits .ai-doc-output/**
```

Run 2 must discover:

```text
docs/foo.md
```

but must not discover:

```text
.ai-doc-output/run-1/candidates/foo.md
```

The same protection must hold for deeper nested generated content:

```text
.ai-doc-output/**
```

not merely files immediately under the output root.

The implementation must not allow recursive accumulation such as:

```text
source
→ candidate
→ candidate-of-candidate
→ candidate-of-candidate-of-candidate
```

across repeated runs.

---

#### Path handling

Use the project's existing normalized/path-aware matching mechanisms.

The protection must not depend on fragile substring matching.

Account for the path representations already supported by the project, including relevant relative-path normalization and platform differences.

Do not introduce an unrelated filesystem abstraction as part of this fix.

---

#### Observability

Do not add new telemetry solely for skipped tool-owned output unless the existing observation model already has a natural, low-cost place for such a fact.

Preventing self-ingestion is a correctness invariant, not an analyzer finding.

Do not emit one warning per skipped generated file.

Normal protection should be silent.

If existing discovery diagnostics expose aggregate skipped-file information naturally, preserving that behavior is sufficient.

---

#### Tests

Add focused regression coverage for at least the following cases.

**Case A — default config**

```text
.ai-doc-output/generated.md exists
default configuration

→ generated.md is not an optimization source
```

This preserves existing behavior.

**Case B — explicit config loses default exclusion**

```yaml
include:
  - "**/*.md"

exclude:
  - "vendor/**"
```

with:

```text
docs/source.md
.ai-doc-output/run/candidates/generated.md
```

Expected:

```text
docs/source.md
    → discovered as optimization source

.ai-doc-output/run/candidates/generated.md
    → not discovered as optimization source
```

This is the primary regression case.

**Case C — nested scratch output**

```text
.ai-doc-output/a/b/c/candidate.md
```

must remain protected.

**Case D — repeated optimization runs**

Create or simulate output from a previous optimization run, then perform source discovery for a subsequent run.

Previously generated candidates must not become new optimization inputs.

**Case E — broad user include**

A broad pattern such as:

```yaml
include:
  - "**/*.md"
```

must not override the core optimization-output protection.

**Case F — unrelated project Markdown remains discoverable**

Verify that the new protection does not accidentally suppress ordinary project Markdown outside the protected output root.

**Case G — generic discovery behavior**

Where the architecture exposes generic discovery independently from optimization-source discovery, verify that the fix does not unnecessarily make `.ai-doc-output/**` globally impossible to inspect through unrelated workflows.

**Case H — custom output root**

If custom `--output` protection can be implemented without material lifecycle restructuring:

```bash
--output tmp/optimizer-results
```

must prevent Markdown beneath that root from becoming optimization source input.

If this cannot be implemented narrowly, document the remaining gap rather than introducing a large orchestration refactor.

Tests must not depend on network access or external providers.

---

#### Non-goals

Do not:

- introduce config inheritance;
- merge explicit config with root config;
- redesign Markdown discovery;
- redesign optimizer execution order solely for this fix;
- introduce a new filesystem abstraction;
- make all `.ai-doc-output` files globally inaccessible;
- delete previous optimization output automatically;
- clean old output directories;
- redesign output retention;
- add output garbage collection;
- add broad generated-file detection heuristics;
- classify arbitrary generated Markdown as unsafe;
- rely on users remembering the correct exclude pattern.

The goal is narrowly:

> enforce the boundary that `ai-doc` optimization artifacts are generated state, not optimization source documents, and prevent the optimizer from recursively consuming its own scratch output.

### P1-1 — Reduce Duplicate-Finding Noise Without Hiding Real Duplication

#### Problem

Real downstream dogfooding exposed excessive `FINOPS_DUPLICATE_LIST_ITEM` findings, particularly in Markdown documents with weak or absent heading structure.

High-volume duplicate findings reduce the usefulness of the analyzer:

- important findings become harder to notice;
- repeated low-value findings dominate reports;
- users become incentivized to ignore the analyzer;
- downstream automation receives a distorted signal;
- finding count increases without a corresponding increase in actionable information.

For `ai-doc`, this is not merely cosmetic.

The analyzer should optimize for **signal quality**, not maximum finding count.

However, the initial diagnosis that heading-less documents create duplication simply because all units have `section=None` is incomplete.

Before changing behavior, verify the current implementation.

The existing duplication logic groups units by normalized content. A missing section heading does not, by itself, make unrelated list items duplicates.

Therefore this task must address the demonstrated noise without introducing blanket suppression that hides legitimate repeated content.

---

#### Core principle

A duplicate finding should represent a useful duplication signal, not merely another occurrence of an already-reported local repetition.

At the same time:

> real cross-document duplication must remain detectable even when the affected documents have no headings.

Do not solve false-positive/noise problems by disabling duplication analysis for heading-less Markdown.

---

#### 1. Verify and characterize the observed duplicate noise first

Before modifying the analyzer, reproduce the problematic behavior with focused fixtures representative of the real integration.

Determine what actually produces the excessive findings.

At minimum distinguish:

```text id="fr6uzc"
same normalized item repeated inside one document

same normalized item repeated across multiple documents

same item repeated multiple times inside A
and multiple times inside B

structurally generic Markdown list fragments

meaningful duplicated instruction/reference content
```

Inspect the current grouping and finding-emission behavior rather than assuming `section=None` is the root cause.

The implementation should fix the demonstrated amplification mechanism.

Do not introduce a speculative heuristic if the reproduced behavior points to a narrower cause.

---

#### 2. Collapse redundant intra-document duplicate noise

When the same normalized list item occurs repeatedly within one document, avoid emitting a separate equivalent finding for every occurrence when those findings communicate the same underlying problem.

Prefer one useful aggregate finding for the duplicated content within the relevant document/scope.

For example, conceptually:

```text id="20wdmg"
- Run tests.
- Run tests.
- Run tests.
```

should not require three effectively identical findings to communicate:

> this document repeats the same list item.

The finding may preserve useful evidence such as occurrence count and representative locations if supported naturally by the existing finding model.

Do not redesign the entire finding schema solely to expose occurrence metadata.

The exact aggregation shape should follow the existing analyzer/reporting architecture.

---

#### 3. Preserve real cross-document duplication

Do not suppress duplication merely because:

```text id="bsvsdr"
section is None
```

or because documents have no headings.

For example:

```text id="izg2p0"
docs/a.md:
- Always run the migration validation before deployment.

docs/b.md:
- Always run the migration validation before deployment.
```

may represent genuine duplicated project knowledge and must remain eligible for duplication reporting even if neither file contains headings.

Likewise, if repeated content exists both intra-document and cross-document, aggregation must not erase the fact that the content is duplicated across document boundaries.

The implementation should distinguish:

```text id="83ooyr"
repeated occurrences
```

from:

```text id="73dy3j"
distinct duplication scopes
```

rather than treating every textual occurrence as an equally valuable independent finding.

---

#### 4. Add a structural signal for materially heading-less Markdown where appropriate

If a Markdown document contains substantial structured/list-oriented content but lacks useful heading structure, that is primarily a **structure** problem rather than a reason to flood duplication findings.

Add or reuse an appropriate structure finding representing the condition, conceptually:

```text id="3rua5c"
STRUCTURE_NO_HEADINGS
```

Exact naming should follow existing finding-code conventions.

This finding should not fire for every tiny Markdown fragment.

Use a conservative threshold or existing document/section semantics so that trivial files are not reported merely for lacking a heading.

The purpose is to communicate:

> this document has enough content that missing structure reduces analyzability/readability.

Do not make the structure finding a prerequisite for duplication analysis.

Do not automatically suppress all duplicate findings whenever it fires.

The two signals describe different problems:

```text id="gplq27"
STRUCTURE_NO_HEADINGS
    → document organization problem

FINOPS_DUPLICATE_LIST_ITEM
    → duplicated-content problem
```

---

#### 5. Prefer aggregation over blanket suppression

When duplicate findings are technically valid but excessively repetitive, prefer reducing redundant emissions rather than disabling the rule.

The desired progression is:

```text id="u5fywo"
many equivalent low-information findings
                ↓
small number of representative actionable findings
```

not:

```text id="h30vhh"
many findings
    ↓
disable rule for this document class
    ↓
zero signal
```

In particular, do not add logic equivalent to:

```python id="v34eyk"
if section is None:
    return []
```

or:

```python id="j6mg2c"
if document_has_no_headings:
    disable_duplicate_analysis()
```

Those fixes would hide legitimate duplication.

---

#### 6. Preserve deterministic behavior

Duplicate aggregation and structural detection must remain deterministic.

Given identical documents and configuration, finding identity/count/order must not depend on:

- filesystem traversal accidents;
- dictionary/set iteration order;
- external models;
- network access;
- semantic providers.

If representative evidence must be selected from several occurrences, use a stable deterministic rule consistent with existing ordering.

---

#### Tests

Add regression coverage based on the reproduced failure mode.

At minimum cover:

**Case A — repeated item inside one heading-less document**

```text id="dk3ovf"
same normalized list item appears several times
inside one substantial heading-less document
```

Expected:

```text id="mwglrx"
→ duplication remains detectable
→ redundant equivalent findings are collapsed
→ report is not flooded per occurrence
```

---

**Case B — unrelated items in a heading-less document**

```text id="xzhv98"
- Install dependencies.
- Run unit tests.
- Deploy staging.
```

Expected:

```text id="3k0m5o"
→ absence of headings alone does not create duplicate findings
```

This explicitly guards against encoding the incorrect `section=None` diagnosis into the implementation.

---

**Case C — cross-document duplicate without headings**

```text id="zow7k7"
a.md:
- Always validate migrations before deployment.

b.md:
- Always validate migrations before deployment.
```

Expected:

```text id="s9hzch"
→ genuine cross-document duplication remains detectable
```

---

**Case D — repeated occurrences across multiple documents**

When the same normalized content occurs multiple times in multiple documents:

```text id="4oxxgv"
A: 3 occurrences
B: 2 occurrences
```

the analyzer should preserve the cross-document signal without emitting an unnecessary combinatorial or per-occurrence flood.

Assert the intended aggregate behavior explicitly.

---

**Case E — substantial heading-less document**

A sufficiently substantial Markdown document with meaningful body/list content and no headings should produce the new/reused structural signal where applicable.

---

**Case F — trivial heading-less fragment**

A tiny Markdown fragment should not receive a structural warning merely because it lacks a heading.

---

**Case G — existing meaningful duplicate behavior**

Preserve at least one existing representative duplication case that was already considered valid before this change.

This is important: the regression suite must prove both:

```text id="e9qclb"
noise decreased
AND
real duplicate signal survived
```

---

#### Acceptance criteria

The task is complete when:

1. the real duplicate-noise pattern can be reproduced by a focused test;
2. the actual amplification mechanism is understood and corrected;
3. equivalent intra-document duplicate findings no longer flood the report;
4. genuine cross-document duplication remains detectable;
5. heading-less documents are not blanket-exempted from duplication analysis;
6. substantial missing document structure can be represented as a structural finding where appropriate;
7. unrelated heading-less list items do not become duplicate findings;
8. behavior remains deterministic;
9. no semantic provider or external service is required;
10. existing meaningful duplicate detection remains covered by regression tests.

---

#### Non-goals

Do not:

- disable duplication analysis for heading-less documents;
- treat `section=None` as proof of duplication;
- suppress all intra-document duplication;
- remove cross-document duplication detection;
- add semantic/embedding-based duplicate detection;
- add LLM duplicate classification;
- redesign the evidence pyramid;
- redesign the finding model solely for aggregation metadata;
- redesign Markdown parsing;
- redesign document profiles;
- introduce configurable false-positive thresholds without demonstrated need;
- optimize for reducing finding count at the expense of real signal.

The goal is narrowly:

> reduce redundant duplicate-finding noise observed during real dogfooding while preserving meaningful intra-document and cross-document duplication signals.

### P1-2 — Verify and Complete Project-Level Analyzer Heuristic Adaptation

#### Problem

Real downstream dogfooding produced questionable `CLARITY_NO_ACTIONABLE_CONTENT` findings for sections that may intentionally contain reference/context material inside otherwise instructional documents.

Examples include sections conceptually similar to:

```text id="o0bdcf"
Architecture
Background
Project Context
Reference
```

This does **not** necessarily mean the core `ClarityAnalyzer` heuristic is wrong.

A document with profile:

```text id="0vehl3"
INSTRUCTION
```

may legitimately contain individual sections whose project-specific purpose is descriptive rather than actionable.

Encoding project-specific section semantics into core through an expanding list of heading-name exceptions would create brittle global behavior.

The preferred model is:

```text id="6t9ybg"
generic core analyzer
        +
project-specific knowledge
        ↓
project-level analyzer adaptation
```

`ai-doc` already has a project extension architecture intended to allow project-local analyzer behavior.

This task must verify whether that architecture is actually sufficient, usable, and documented for this real integration case.

If it already is, do not add another mechanism.

If it is not, implement the smallest missing capability required to support the use case through the existing extension architecture.

---

#### Target use case

A project must be able to adapt a core analyzer heuristic such as:

```text id="71tbwg"
CLARITY_NO_ACTIONABLE_CONTENT
```

based on project-specific knowledge without modifying or forking `ai-doc` core.

For example, a downstream project may know that:

```text id="dlvzm7"
Architecture
Project Context
Background
```

are intentionally descriptive sections even when they occur inside an `INSTRUCTION` document.

The project should be able to suppress, replace, refine, or otherwise adapt the relevant analyzer behavior through the supported project-extension mechanism.

This task does **not** prescribe which of those adaptation strategies must be used internally.

First determine what the existing Analyzer extension contract already supports.

---

#### 1. Audit the existing Analyzer extension path

Before implementing anything, verify the current L3 project-extension behavior end to end.

Inspect at least:

```text id="qed8bs"
.ai-doc.yaml
        ↓
project extension loading
        ↓
register(registry)
        ↓
Analyzer registration/resolution
        ↓
production check/analyze execution
```

Determine whether a project-local extension can currently:

1. register a custom Analyzer;
2. cause that Analyzer to participate in the real CLI production path;
3. replace or supersede the relevant built-in analyzer where necessary;
4. preserve the remaining built-in analyzers;
5. access enough document/section/finding context to implement project-specific heuristic behavior;
6. do so without importing unstable internal implementation details that the public extension contract does not promise.

Do not infer capability merely from the existence of `Analyzer` interfaces or registry code.

Verify the complete causal path through actual production execution.

---

#### 2. Test the concrete dogfooding use case

Create a minimal project-local extension fixture demonstrating the real requirement.

Conceptually, the project should be able to express behavior equivalent to:

```text id="91mnc6"
for CLARITY_NO_ACTIONABLE_CONTENT:

    if section matches project-known reference semantics:
        suppress/refine the finding

    otherwise:
        preserve normal clarity analysis
```

The exact implementation may differ depending on the existing extension architecture.

Do not introduce a generic policy DSL merely to make this example look declarative.

A Python project extension is acceptable and expected if that is the existing L3 mechanism.

The test must exercise the production CLI path rather than proving only that an extension class can be instantiated.

---

#### 3. Prefer composition over copied core logic

A project should not be forced to copy the entire current `ClarityAnalyzer` implementation merely to alter one project-specific heuristic if the existing architecture can reasonably support a narrower composition/delegation pattern.

Preferred conceptual behavior:

```text id="bnyf50"
core analyzer behavior
        ↓
project adaptation
        ↓
final findings
```

or another existing extension-compatible composition mechanism.

However, do not introduce a new middleware/event/filter architecture merely to satisfy this preference.

First inspect what can already be achieved through:

- analyzer replacement;
- analyzer composition;
- registry resolution;
- public finding/document models;
- existing public API.

If replacement plus delegation through public contracts is already sufficient and maintainable, use and document it.

---

#### 4. If the capability already exists, do not redesign it

If the current project Analyzer extension contract already supports the use case cleanly:

- add regression/integration coverage proving it;
- add clear documentation;
- add a minimal example;
- make no architectural change.

The preferred outcome of this task is allowed to be:

```text id="nt9x12"
implementation already sufficient
+
missing test/documentation
```

Do not create a new abstraction simply because this task exists.

---

#### 5. If the capability is missing, implement the smallest extension-contract gap

If the audit demonstrates that project-local analyzer adaptation cannot be implemented cleanly through the supported public extension surface, close only the demonstrated gap.

Examples of legitimate gaps may include:

- project analyzers cannot replace/select a built-in analyzer;
- replacement accidentally removes unrelated analyzers;
- the production CLI does not honor the registered project analyzer;
- necessary public document/finding context is unavailable;
- composition requires importing private core implementation;
- registry resolution does not provide a supported way to select the project implementation.

Choose the smallest correction consistent with the existing extension architecture.

Do not introduce:

- a second extension system;
- generic analyzer middleware;
- arbitrary hooks;
- a global finding-filter framework;
- a new rules engine;
- a project policy language;
- section-profile architecture;

unless the existing extension contract fundamentally cannot satisfy the demonstrated use case and such a change is independently justified.

A real missing capability must be demonstrated before extending the contract.

---

#### 6. Document the supported project-level adaptation pattern

The documentation must show how a project can handle this class of false positive without modifying `ai-doc` core.

Use a concrete example based on `CLARITY_NO_ACTIONABLE_CONTENT`.

The example should demonstrate the supported pattern conceptually equivalent to:

```text id="sv6sgm"
generic ai-doc clarity behavior
+
project knowledge about reference-only sections
=
project-adapted clarity behavior
```

Document:

- where the project extension lives;
- how it is registered;
- how `.ai-doc.yaml` selects/enables it where required;
- how it participates in the real CLI path;
- how it preserves desired core behavior;
- how project-specific suppression/refinement is implemented;
- what public contracts the extension may rely on.

Avoid presenting a company-specific implementation as a universal core rule.

The documentation should make it possible to implement the pattern in another repository without reading `ai-doc` internals.

---

#### 7. Do not hard-code the dogfooding headings into core

This task must not result in core logic such as:

```python id="wm04tz"
REFERENCE_HEADINGS = {
    "architecture",
    "background",
    "context",
    "project context",
    "reference",
}
```

solely because those headings produced questionable findings in one downstream repository.

Heading names do not have universal semantics.

For example:

```md id="0e8j0n"
## Architecture

Always update the architecture diagram after changing
service boundaries.
```

is actionable despite its heading.

Likewise:

```md id="99m0v7"
## Deployment

Production deployment is managed by ArgoCD...
```

may be purely descriptive despite a seemingly operational heading.

Project knowledge belongs in the project adaptation layer unless repeated independent evidence demonstrates a universal core heuristic.

---

#### 8. Preserve core analyzer behavior by default

Without a project extension, existing core behavior must remain unchanged unless the audit discovers a separate correctness bug.

In particular:

```text id="2m21j3"
plain ai-doc installation
        ↓
existing ClarityAnalyzer semantics
```

must remain stable.

The project adapter must affect only projects that explicitly register/select it through the supported extension mechanism.

No project-specific heuristic should leak into unrelated repositories.

---

#### Tests

Add focused coverage for at least the following cases.

**Case A — stock core behavior**

Without a project extension, a representative section that currently triggers:

```text id="cytylp"
CLARITY_NO_ACTIONABLE_CONTENT
```

continues to behave according to existing core semantics.

---

**Case B — project extension is causally active**

With the project extension registered through the supported L3 mechanism:

```text id="un38mo"
same document
same section
same core installation
```

produces the project-adapted result.

This must be exercised through the real CLI production path.

---

**Case C — targeted adaptation**

A project-known reference-only section can suppress/refine the unwanted finding.

---

**Case D — unrelated actionable/instructional section**

A section outside the project-specific exception remains subject to normal clarity analysis.

The adapter must not accidentally disable the entire analyzer.

---

**Case E — unrelated analyzers survive**

Registering/selecting the project clarity adaptation must not silently remove unrelated built-in analyzer capabilities.

---

**Case F — no private implementation dependency**

Where practical, ensure the example/test uses the supported public extension/API surface rather than importing private `ai_doc` implementation modules merely to make the test pass.

---

#### Acceptance criteria

The task is complete when one of the following outcomes is demonstrated.

**Outcome A — existing architecture is sufficient**

```text id="2z1zv5"
project-level analyzer adaptation already works
        +
production-path test proves it
        +
documentation/example explains it
        +
no new architecture added
```

or:

**Outcome B — a real extension gap exists**

```text id="jq2d4e"
existing architecture cannot cleanly support the use case
        ↓
smallest missing extension capability implemented
        ↓
production-path test proves it
        ↓
documentation/example explains it
```

In either outcome, a downstream project must be able to address this class of project-specific analyzer false positive without forking `ai-doc` core.

---

#### Non-goals

Do not:

- hard-code reference-heading names into core;
- suppress `CLARITY_NO_ACTIONABLE_CONTENT` globally;
- lower its severity globally solely because of this dogfooding case;
- add `SectionProfile`;
- add a project policy DSL;
- add generic finding middleware without demonstrated need;
- add a rules engine;
- redesign Analyzer contracts if the existing contract is sufficient;
- redesign the extension registry;
- change unrelated analyzer heuristics;
- copy company-specific rules into the public package.

The goal is narrowly:

> verify that project-specific analyzer heuristics can be implemented through the supported project extension architecture, document the pattern, and close only the smallest demonstrated extension gap if they cannot.

### P1-3 — Make Orphan Detection Respect Runtime Reachability Semantics

#### Problem

`STRUCTURE_ORPHANED_AI_DOC` currently treats Markdown inbound-link reachability as evidence that an AI-facing document is connected to the rest of the documentation graph.

This is useful for ordinary instruction documents whose intended reachability is represented by Markdown links.

However, the current structure logic also applies orphan detection to:

```text
DocumentProfile.SKILL
```

A skill document may intentionally have no inbound Markdown links because it is discovered and loaded on demand by the relevant agent/runtime mechanism.

In that case:

```text
no inbound Markdown link
```

does **not** imply:

```text
document is unreachable / orphaned
```

Real downstream dogfooding exposed this as a false-positive source.

The problem is conceptual:

> Markdown graph reachability and AI runtime reachability are not universally equivalent.

`ai-doc` already models concepts such as `DocumentProfile.SKILL` and `LoadingConfig.mode`. The structure analyzer must respect the semantics of those existing concepts rather than introducing a parallel mechanism solely to suppress orphan findings.

---

#### Core invariant

`STRUCTURE_ORPHANED_AI_DOC` should only fire when lack of inbound Markdown reachability is meaningful for the document's actual discovery/loading semantics.

Conceptually:

```text
Markdown inbound link
        ↓
one possible reachability mechanism
```

not:

```text
Markdown inbound link
        ↓
the universal definition of runtime reachability
```

A document that is intentionally independently discoverable or loaded on demand must not be classified as orphaned merely because another Markdown document does not link to it.

---

#### 1. Audit the existing reachability semantics before changing behavior

Before implementing the fix, verify the current contracts for:

```text
DocumentProfile.SKILL
LoadingConfig.mode
profile auto-detection
StructureAnalyzer orphan detection
FinOps/loading behavior
```

Answer from the current implementation and documentation:

1. What does `DocumentProfile.SKILL` semantically represent?
2. Are `SKILL` documents expected to be independently/on-demand discoverable?
3. Which file conventions are automatically classified as `SKILL`?
4. What exactly does `LoadingConfig.mode == "on_demand"` mean today?
5. Is `on_demand` merely a FinOps/context-loading estimate, or does it assert independent runtime reachability?
6. Does `StructureAnalyzer` currently have access to enough information to distinguish these cases?
7. Are there other existing profiles/loading modes whose reachability does not depend on inbound Markdown links?

Do not assume that two similarly named concepts have identical semantics.

In particular:

> do not suppress orphan findings for every `loading.mode == "on_demand"` document unless the existing contract actually establishes that such a document has an independent discovery mechanism.

---

#### 2. Fix `SKILL` orphan false positives if the existing profile contract confirms independent discovery

If the audit confirms that `DocumentProfile.SKILL` represents documents intentionally discoverable independently of Markdown links, then `SKILL` documents must not receive:

```text
STRUCTURE_ORPHANED_AI_DOC
```

solely because they have zero inbound Markdown links.

For example:

```text
.claude/skills/review/SKILL.md
```

or another supported skill convention may legitimately be:

```text
Markdown graph:
    zero inbound links

runtime:
    discoverable as a skill
```

That state must not be reported as orphaned.

Prefer expressing the implementation in terms of reachability semantics rather than introducing another arbitrary exception flag.

---

#### 3. Preserve orphan detection where Markdown reachability remains meaningful

Do not globally weaken `STRUCTURE_ORPHANED_AI_DOC`.

For an ordinary instruction document whose expected connection to the AI documentation graph is represented through Markdown references, lack of inbound links may remain a useful signal.

Conceptually:

```text
ordinary INSTRUCTION
+ no independent discovery semantics
+ zero inbound reachability
    ↓
STRUCTURE_ORPHANED_AI_DOC may still be valid
```

The fix must therefore distinguish document semantics rather than simply reducing finding count.

---

#### 4. Evaluate `LoadingConfig.mode == "on_demand"` separately

The existing loading configuration may provide a broader representation of documents that are not always loaded.

Do not automatically equate:

```text
loading.mode == "on_demand"
```

with:

```text
independently runtime-discoverable
```

unless the current domain contract supports that interpretation.

If the audit confirms that `on_demand` explicitly means that a document is reachable through a mechanism independent of Markdown links, reuse that existing concept in orphan detection.

If the audit shows that `on_demand` currently means only something such as:

```text
not always present in context
```

or is primarily used for FinOps/loading-cost modeling, do not silently broaden its semantics as part of this task.

In that case:

- fix the demonstrated `SKILL` case;
- document the distinction;
- leave broader loading-mode reachability for a separately justified change.

Do not create ambiguous coupling between FinOps assumptions and structural reachability.

---

#### 5. Reuse existing domain concepts

Do not solve this problem by introducing redundant configuration such as:

```text
ignore_orphan: true
```

or:

```text
orphan_exempt: true
```

or a new profile such as:

```text
DocumentProfile.ON_DEMAND
```

unless the audit demonstrates that the existing domain model genuinely cannot represent the required semantics.

The preferred model is:

```text
existing document/profile/loading semantics
        ↓
reachability interpretation
        ↓
orphan analysis
```

not:

```text
existing semantics
+
new orphan-specific exception system
```

The false positive should be corrected at the semantic boundary that already owns the relevant information.

---

#### 6. Keep Markdown graph information truthful

Exempting an independently discoverable document from `STRUCTURE_ORPHANED_AI_DOC` must not falsify the underlying Markdown graph.

For example, if a skill has:

```text
inbound Markdown links == 0
```

that fact remains true.

Do not manufacture synthetic Markdown edges merely to make the document appear connected.

The correct interpretation is:

```text
Markdown graph:
    no inbound edge

runtime reachability:
    independently discoverable

orphan finding:
    not applicable
```

This distinction must remain explicit in the implementation.

---

#### 7. Document the reachability model clearly and prominently

This behavior must be explicitly documented.

Do not leave the distinction discoverable only by reading `StructureAnalyzer` source code.

Documentation must explain that `ai-doc` distinguishes:

```text
Markdown graph reachability
```

from:

```text
runtime/discovery reachability
```

and that an orphan finding is only meaningful where Markdown linkage is an expected reachability mechanism.

At minimum document:

- what `STRUCTURE_ORPHANED_AI_DOC` means;
- what it does **not** mean;
- why zero inbound Markdown links do not universally imply an orphan;
- how `DocumentProfile.SKILL` participates in reachability semantics;
- whether `SKILL` documents are exempt from orphan detection and why;
- the relationship, if any, between `LoadingConfig.mode` and orphan detection;
- whether `on_demand` currently implies runtime reachability or merely loading behavior;
- examples of documents that should and should not be considered orphaned.

The documentation should include a concrete contrast similar to:

```text
Ordinary instruction document
    no inbound link
    no independent discovery mechanism
    → may be orphaned

Skill document
    no inbound link
    discovered by the agent/runtime skill mechanism
    → not orphaned merely because Markdown does not link to it
```

If `LoadingConfig.mode == "on_demand"` is **not** sufficient to establish independent reachability, document that explicitly as well.

Avoid vague wording such as:

> Some documents may not need links.

State the actual supported semantics.

---

#### 8. Keep discovery, loading, and reachability terminology distinct

Documentation and code naming must not collapse the following concepts:

```text
discovered by ai-doc
loaded into AI context
reachable through Markdown links
discoverable by an external AI runtime
always loaded
loaded on demand
```

They may interact, but they are not automatically equivalent.

This task should make the relevant distinction clearer, not introduce another overloaded meaning of "discovery" or "loading."

If existing documentation currently conflates these concepts in the area touched by this task, correct that documentation narrowly.

Do not undertake a broad documentation rewrite.

---

#### Tests

Add focused regression coverage for at least the following cases.

**Case A — independently discoverable skill with no inbound link**

```text
profile == SKILL
inbound links == 0
```

where the existing SKILL contract establishes independent discovery.

Expected:

```text
→ no STRUCTURE_ORPHANED_AI_DOC
```

This is the primary regression case.

---

**Case B — skill with inbound link**

```text
profile == SKILL
inbound links > 0
```

Expected:

```text
→ no orphan finding
→ no synthetic or otherwise altered graph semantics
```

---

**Case C — ordinary orphaned instruction**

```text
profile == INSTRUCTION
inbound links == 0
no existing independent reachability semantics
```

Expected:

```text
→ existing STRUCTURE_ORPHANED_AI_DOC behavior preserved
```

This proves that the fix did not globally disable orphan detection.

---

**Case D — reachable instruction**

```text
profile == INSTRUCTION
inbound links > 0
```

Expected:

```text
→ no orphan finding
```

Preserve existing valid behavior.

---

**Case E — `on_demand` semantics**

Add a test reflecting the result of the loading-semantics audit.

If `on_demand` is confirmed to assert independent runtime reachability:

```text
on_demand
+ zero inbound links
→ no orphan finding
```

If it is **not** confirmed to mean that:

```text
on_demand
+ zero inbound links
→ do not silently change existing orphan semantics
```

The test must encode the documented contract rather than an assumption based on the name.

---

**Case F — auto-detected skill**

Where supported by the current test infrastructure, exercise at least one real skill path convention through profile detection and structure analysis rather than constructing only a synthetic `Document(profile=SKILL)`.

This verifies the complete behavior:

```text
real skill path
    ↓
profile detection
    ↓
SKILL
    ↓
structure analysis
    ↓
no false orphan
```

---

#### Acceptance criteria

The task is complete when:

1. the semantics of `DocumentProfile.SKILL` and `LoadingConfig.mode` have been verified against current implementation;
2. independently discoverable skills are not reported as orphaned merely because they lack inbound Markdown links;
3. ordinary instruction orphan detection remains functional;
4. no synthetic graph edges are introduced;
5. no redundant `ignore_orphan`-style configuration is added without demonstrated necessity;
6. `on_demand` affects orphan analysis only if its existing contract justifies that interpretation;
7. regression tests cover both the removed false positive and preserved true-positive behavior;
8. the reachability model is clearly documented;
9. the documentation explicitly distinguishes Markdown graph reachability from runtime/discovery reachability;
10. a maintainer can understand from the documentation alone why an unlinked `SKILL.md` may be valid and why an unlinked ordinary instruction document may still be reported.

---

#### Non-goals

Do not:

- disable orphan detection globally;
- classify every unlinked document as valid;
- manufacture Markdown graph edges for skills;
- add `ignore_orphan` solely for this case;
- add `orphan_exempt` solely for this case;
- add `DocumentProfile.ON_DEMAND`;
- assume `LoadingConfig.on_demand` means runtime reachability without verifying its contract;
- redesign the document graph;
- redesign profile detection;
- redesign loading/FinOps modeling;
- introduce a generic reachability framework unless the current architecture demonstrably requires one;
- move project-specific reachability rules into core.

The goal is narrowly:

> make orphan detection respect existing runtime/discovery semantics, remove false orphan findings for independently discoverable documents such as skills, and make the distinction between Markdown linkage and runtime reachability explicit and obvious in the documentation.

### P2-1 — Evaluate and, If Justified, Promote Gated Evidence Execution into Core

#### Motivation

Real downstream integration introduced a useful execution pattern around `ai-doc`:

```text id="8sn2lf"
cheap / deterministic evidence
        ↓
stronger local evidence
        ↓
expensive semantic evidence
```

The practical goal is simple:

> use the cheapest sufficient evidence first and escalate to more expensive evaluation only when earlier evidence is insufficient.

This aligns with existing `ai-doc` principles:

- deterministic-by-default execution;
- conservative zero-spend behavior;
- explicit semantic-provider usage;
- evidence-tier separation;
- budget awareness;
- epistemic honesty;
- semantic evaluation only when justified.

The downstream integration therefore may not represent company-specific behavior. It may expose a missing generic execution policy over capabilities that already exist in `ai-doc`.

However, one downstream implementation is not sufficient evidence to introduce a new orchestration framework.

This task must determine whether the pattern can be expressed as a thin, generic composition of existing core capabilities.

If yes, promote it into core.

If doing so requires a substantial new orchestration abstraction, pipeline framework, DAG, DSL, or optimizer redesign, defer implementation.

---

#### Core question

Determine whether `ai-doc` should provide a first-class execution policy equivalent to:

```text id="lnd7u1"
start with cheapest applicable evidence
        ↓
accept/reject/stop when evidence is sufficient
        ↓
escalate only when necessary
        ↓
avoid expensive semantic work when cheaper evidence already decides
```

The task is **not** to copy the exact downstream pipeline into core.

The task is to determine whether the underlying execution policy is generic enough to belong to `ai-doc`.

---

#### 1. Audit the existing evidence stages and execution paths

Before implementing anything, map the relevant existing capabilities and their current production execution paths.

Inspect at least the existing mechanisms for:

```text id="uzv63o"
deterministic / Tier-0 checks
local semantic or NLI evaluation, where present
lexical / non-provider evidence
deep evaluation, where present
pairwise semantic judging
budget / cost gates
candidate rejection
optimizer stop conditions
provider execution
```

For each relevant stage, determine:

- whether it is already represented as a stable core concept;
- whether it already has a production execution path;
- whether it can be composed without importing private implementation details;
- whether it produces a sufficiently explicit outcome to support escalation decisions;
- whether it may incur external/provider cost;
- whether it is optional;
- whether it is applicable to every optimization mode/profile or only some.

Do not infer a universal tier order merely from current naming.

---

#### 2. Compare the downstream cascade with existing core concepts

Determine whether the real downstream cascade is fundamentally:

```text id="y85b9j"
composition of existing ai-doc capabilities
```

or:

```text id="h42sbs"
a project-specific workflow that happens to call ai-doc
```

A generic core policy is justified only if most of the behavior can be expressed through existing core concepts without importing downstream-specific assumptions.

In particular, do not automatically canonize an exact sequence such as:

```text id="1w0q0d"
Tier 0
→ local NLI
→ lexical gate
→ pairwise semantic
```

Verify whether that ordering is semantically justified by the current architecture.

Questions to answer include:

- Is local NLI always cheaper or logically earlier than lexical evidence?
- Are both stages universally available?
- Is either stage optional?
- Where does deep evaluation belong, if anywhere?
- Are some stages alternative evidence mechanisms rather than sequential tiers?
- Does applicability vary by profile or optimization mode?
- Can a stage return an explicit "insufficient evidence / continue" outcome?
- Can provider-backed stages be skipped cleanly when earlier evidence is decisive?

Do not force capabilities into a linear pipeline if their existing semantics do not support one.

---

#### 3. Define the smallest useful generic policy

If the audit supports promotion into core, define the smallest generic policy necessary to express:

> cheapest sufficient evidence first.

Prefer a thin policy over existing execution stages.

Conceptually:

```text id="cj3o47"
candidate
    ↓
cheap deterministic evidence
    ↓
decisive? ── yes → stop
    │
    no
    ↓
next applicable evidence
    ↓
decisive? ── yes → stop
    │
    no
    ↓
expensive semantic evidence
```

The implementation does not need to use this exact representation.

The important properties are:

- stages remain existing domain capabilities where possible;
- expensive work is not performed unnecessarily;
- unavailable optional stages can be handled explicitly;
- execution remains deterministic until a configured semantic/provider stage is actually required;
- escalation decisions are explicit and testable.

---

#### 4. Prefer an execution policy, not a pipeline framework

If implementation is justified, prefer something conceptually comparable to:

```text id="9c6ewx"
GatedEvidencePolicy
```

or an equivalent existing-domain abstraction.

Do not interpret that example as a required class name.

The implementation should coordinate existing capabilities rather than create a second representation of them.

Avoid introducing:

- generic workflow engines;
- arbitrary DAG execution;
- YAML pipeline DSLs;
- generic stage/plugin frameworks;
- event buses;
- workflow schedulers;
- cross-tool orchestration contracts.

This is an `ai-doc` execution policy, not a general-purpose orchestration product.

---

#### 5. Preserve conservative zero-spend behavior

A gated mode must never introduce provider spending merely because the mode is enabled.

The intended behavior is:

```text id="11f1x8"
cheap evidence decisive
        ↓
expensive provider stage not executed
        ↓
zero provider spend for that stage
```

If an expensive semantic stage becomes necessary but no valid provider/model is explicitly configured, preserve existing fail-closed semantics.

Do not:

- silently select OpenAI;
- silently select Claude;
- infer a provider from environment variables;
- fall back to another provider;
- perform network calls merely to determine whether escalation is possible.

Existing provider and budget contracts remain authoritative.

---

#### 6. Preserve epistemic honesty

A gated execution policy must distinguish:

```text id="r3xrb3"
stage not needed

stage unavailable

stage skipped by policy

stage attempted

stage produced uncertain evidence

stage produced decisive evidence
```

where those distinctions are relevant to the existing domain model.

Do not report:

```text id="pm1h43"
semantic verified
```

when semantic evaluation was never reached.

Likewise, a candidate rejected by a deterministic gate must not be represented as having failed semantic evaluation.

The execution policy must compose correctly with the pairwise execution truthfulness introduced by P0-1.

In particular, gated execution must not bypass or falsify:

```text id="0xfvxh"
pairwise_semantic_requested
pairwise_comparisons_performed
--require-pairwise-semantic
```

If strict pairwise semantic evidence is required, an earlier gate must not allow the run to masquerade as satisfying that postcondition.

---

#### 7. Integrate with existing observations where facts are already available

If gated execution is implemented, expose its already-known machine execution facts through the existing local observation mechanism where this can be done without redesigning observability.

Useful facts may include:

```text id="d3ekqc"
which evidence stages were reached
which stages were skipped
where candidates stopped
whether escalation occurred
whether provider-backed evidence was reached
```

Reuse existing stop/rejection/evaluation state where possible.

Do not create a second execution taxonomy solely for telemetry.

Do not implement derived analytics in this task.

The observation principle remains:

> record facts now; derive interpretations later.

Future offline analysis may use these observations to determine whether the chosen gate order actually saves cost while preserving useful evidence.

---

#### 8. CLI surface must remain small

If a generic policy is implemented, expose it through the smallest CLI/config surface consistent with existing command design.

A mode conceptually similar to:

```bash id="o7i2wg"
ai-doc optimize ... --gated
```

may be appropriate.

The exact naming must follow current CLI conventions after inspecting them.

Do not add a separate flag for every internal evidence stage unless such flags already exist and are independently meaningful.

Do not expose implementation details of the cascade merely because they exist internally.

The CLI should communicate the policy:

> escalate through applicable evidence conservatively.

It should not require users to manually reconstruct the internal pipeline.

---

#### 9. Document the policy explicitly if implemented

If gated execution is promoted into core, document:

- what problem it solves;
- the "cheapest sufficient evidence first" principle;
- which existing evidence mechanisms participate;
- which stages are optional;
- when provider-backed evaluation can occur;
- how zero-spend behavior is preserved;
- what happens when an optional stage is unavailable;
- how strict semantic requirements interact with early gates;
- how execution facts appear in reports/observations;
- what the policy does **not** guarantee.

Do not document one exact tier sequence as permanent architecture unless the implementation contract actually guarantees that sequence.

Clearly distinguish:

```text id="fkmn2d"
evidence capabilities
```

from:

```text id="p5i01a"
execution policy over those capabilities
```

---

#### 10. Explicit stop condition for implementation scope

After the audit, do **not** implement the feature if supporting it cleanly requires substantial introduction or redesign of:

- optimizer orchestration;
- generic pipeline infrastructure;
- stage lifecycle architecture;
- extension contracts;
- configuration inheritance;
- generic workflow definitions;
- provider abstractions;
- cross-tool execution contracts.

In that case, produce a concise implementation note documenting:

```text id="hmkg52"
what existing capabilities were inspected
which parts of the downstream cascade are generic
which parts remain project-specific
what architectural gap prevents a thin core policy
what evidence would justify revisiting it later
```

and leave the downstream wrapper in place.

A justified decision **not to implement** is a valid successful outcome of this P2 task.

---

#### Tests — if implementation is justified

If a core gated policy is implemented, add focused behavioral tests covering at least:

**Case A — cheap evidence is decisive**

```text id="6jnj13"
early deterministic evidence decides candidate
→ later expensive semantic stage not called
→ provider call count remains zero for that stage
```

**Case B — escalation is required**

```text id="j2qvn5"
early evidence insufficient
→ next applicable stage executes
```

**Case C — semantic escalation**

```text id="6n45r2"
cheap/local evidence insufficient
→ configured semantic stage executes
→ execution state reports that it actually occurred
```

**Case D — unavailable optional stage**

Verify the documented behavior when an intermediate optional capability is unavailable.

It must not silently substitute an unrelated provider/capability.

**Case E — provider required but not configured**

Where escalation genuinely requires provider-backed evaluation:

```text id="n5mj4r"
→ existing fail-closed behavior preserved
→ no implicit provider selection
```

**Case F — budget prevents escalation**

Existing budget behavior remains authoritative and explicit.

Do not perform provider work beyond the allowed budget merely because gated mode requested escalation.

**Case G — strict pairwise requirement**

```text id="d0o4ge"
--require-pairwise-semantic
```

must retain the P0-1 postcondition.

An early gate alone cannot satisfy it.

**Case H — deterministic repeatability**

With provider-backed stages not reached, repeated runs over identical inputs/configuration produce equivalent gated decisions.

**Case I — existing non-gated execution**

Existing execution modes remain unchanged when the new policy is not selected.

---

#### Acceptance criteria

This task has two valid completion paths.

##### Outcome A — promote into core

Use this outcome only if the audit demonstrates that the pattern is a natural composition of existing `ai-doc` capabilities.

Completion requires:

1. a small generic gated execution policy;
2. no general-purpose orchestration framework;
3. conservative escalation from cheaper to more expensive evidence;
4. existing provider/budget/fail-closed semantics preserved;
5. correct interaction with P0-1 pairwise execution semantics;
6. focused production-path tests;
7. clear documentation;
8. existing non-gated behavior preserved.

##### Outcome B — defer

Use this outcome if the generic behavior cannot be implemented without substantial new architecture.

Completion then requires:

1. no speculative orchestration implementation;
2. a concise documented audit of the existing capabilities;
3. identification of the concrete architectural gap;
4. separation of generic principles from downstream-specific workflow choices;
5. the downstream wrapper remains the appropriate integration layer for now.

Do not treat Outcome B as a failure of the task.

---

#### Non-goals

Do not:

- copy the downstream pipeline verbatim into core;
- canonize an unverified Tier-0 → NLI → lexical → semantic ordering;
- build a generic workflow engine;
- build a DAG executor;
- introduce a pipeline DSL;
- redesign the optimizer;
- redesign extension contracts;
- redesign provider routing;
- add cross-tool orchestration;
- make expensive semantic evaluation mandatory;
- add implicit provider selection;
- add runtime ROI scoring;
- automatically reorder evidence stages based on observations;
- build analytics or dashboards;
- optimize for architectural elegance over demonstrated utility.

The goal is narrowly:

> determine whether the real-world “cheapest sufficient evidence first” pattern is a generic `ai-doc` execution policy, and promote it into core only if it can be implemented as a thin composition of existing capabilities rather than a new orchestration subsystem.

---

## Execution and Completion Contract

This specification is a bounded post-integration hardening pass.

It is not an invitation to redesign `ai-doc`, clean up adjacent code, generalize every observed pattern, or reopen architecture that has already been stabilized.

### Implementation order

Work through the **To Implement** items in priority order unless a later task is directly blocked by an earlier one.

Where tasks touch related code, shared implementation is acceptable when it is the smallest natural solution, but preserve the behavioral boundaries and acceptance criteria of each task.

Do not merge conceptually separate tasks into a broader redesign merely because they share implementation locations.

### Verify before modifying

For every task:

1. inspect the current implementation;
2. reproduce or verify the described behavior where practical;
3. confirm that the specification's assumptions still match the current repository state;
4. implement the smallest correction that satisfies the intended behavior;
5. add focused regression evidence;
6. preserve unrelated behavior.

Source locations, examples, proposed field names, and conceptual pseudocode in this specification are implementation guidance, not permission to override a better understanding of the current code.

If the repository has evolved and an exact proposed implementation no longer fits, preserve the task's behavioral intent and document the deviation.

### Existing architecture wins by default

Prefer, in order:

```text
existing behavior
    ↓
existing public/domain concept
    ↓
existing extension point
    ↓
small extension of an existing abstraction
    ↓
new abstraction only when demonstrably necessary
```

Do not introduce parallel concepts for behavior the current domain model can already represent.

Do not preserve an implementation idea from this specification when the current code proves that the underlying assumption was wrong.

### Correctness over finding count

For analyzer-related tasks, success is not measured by producing fewer or more findings.

The target is:

> higher signal quality while preserving known valid signal.

A false-positive reduction that suppresses legitimate findings is not a successful fix.

Likewise, adding new findings merely to increase coverage is not a goal.

### Epistemic honesty

Preserve the distinction between:

```text
requested
attempted
executed
skipped
unavailable
uncertain
decisive
```

where relevant.

Do not represent absence of evidence as positive evidence.

Do not report semantic evaluation, validation, judgment, or verification when the corresponding operation did not actually occur.

Human-readable output, machine-readable artifacts, and observations must not materially disagree about execution state.

### Cost and provider safety

Preserve conservative zero-spend behavior.

No task in this specification authorizes:

- implicit provider selection;
- implicit model selection;
- unexpected network access;
- hidden fallback to another provider;
- semantic calls merely to improve diagnostics;
- spending beyond existing configured budget semantics.

Provider-backed work must remain explicit and fail closed according to existing contracts.

### Privacy

Preserve existing privacy guarantees.

Do not introduce logging or observations containing document bodies, prompts, model responses, secrets, credentials, environment values, or other content not already permitted by the established observation contract.

New observability introduced by this specification should record machine facts, not project content.

### Public contracts

Preserve established:

- CLI behavior;
- configuration semantics;
- `ai_doc.api.v1`;
- extension contracts;
- process/wire contracts;
- report/artifact formats;
- observation semantics;

unless a task explicitly requires a behavioral or schema change.

Where a contract must change, make the change deliberate, typed where appropriate, tested, and documented.

Do not create accidental public API merely to simplify an internal implementation.

### Conditional tasks

Some P1/P2 tasks intentionally require investigation before implementation.

For those tasks:

> a well-supported decision that the existing architecture is already sufficient, or that implementation would require unjustified new architecture, is a valid outcome when the task explicitly allows it.

Do not implement speculative infrastructure merely to ensure every task produces code changes.

When implementation is deferred, record:

- what was inspected;
- what was learned;
- why the proposed change is not currently justified;
- what future evidence would justify revisiting it.

### Testing

Prefer behavioral regression tests over implementation-shape tests.

Tests should prove both sides of a corrected boundary where applicable:

```text
problematic behavior is fixed
AND
previously valid behavior still works
```

Do not use real external providers or network access where deterministic test doubles can establish the required behavior.

Run the repository's relevant existing quality gates after implementation.

Do not weaken, delete, or bypass existing tests merely to make the new implementation pass.

### Scope discipline

If a task exposes an adjacent issue that is not necessary to satisfy its acceptance criteria:

```text
record it
do not fix it
```

unless it is a correctness or safety issue that makes the requested implementation invalid.

In particular, do not turn this pass into:

- broad refactoring;
- dead-code cleanup;
- naming cleanup;
- configuration redesign;
- optimizer redesign;
- extension-system redesign;
- orchestration-framework construction;
- documentation restructuring;
- speculative abstraction work.

The existence of nearby technical debt is not sufficient reason to expand scope.

### Documentation

Where a task changes or clarifies a behavioral contract, update the relevant documentation in the same change.

Documentation must describe the behavior that actually exists after implementation.

Do not document planned behavior as implemented behavior.

Examples should exercise supported public surfaces rather than depend on private implementation details.

### Final implementation report

After completing the specification, provide a concise report grouped by task:

```text
P0-1 — implemented
    key behavior:
    tests:
    notable contract changes:

P0-2 — implemented
    ...

P1-2 — existing extension contract was sufficient
    evidence:
    docs/tests added:

P2-1 — deferred
    reason:
    architectural gap:
    revisit when:
```

For every task, classify the result as one of:

```text
implemented
already satisfied
partially implemented with explicit remaining gap
deferred as allowed by the specification
blocked
```

Also report:

- files materially changed;
- public/API/config/artifact schema changes;
- documentation changes;
- tests and quality gates executed;
- any deviations from the specification and why;
- any newly discovered follow-up issues that were intentionally left out of scope.

Do not hide incomplete acceptance criteria behind a general statement that the task is complete.

---

## Definition of Done

This hardening pass is complete when:

1. every To Implement item has an explicit disposition;
2. all implemented behavioral changes have focused regression coverage;
3. relevant documentation matches the resulting behavior;
4. established public contracts remain stable except for deliberate changes required by this specification;
5. deterministic and zero-spend defaults remain intact;
6. provider-backed behavior remains explicit and fail-closed;
7. observation/privacy guarantees remain intact;
8. relevant repository quality gates pass;
9. conditional tasks that were not implemented have a documented technical reason;
10. no unrelated architecture or cleanup work has been introduced.

Once these conditions are satisfied:

> **stop.**

Do not continue with opportunistic cleanup, architecture polishing, additional heuristics, or speculative improvements.

The next source of requirements should be further real-world dogfooding and accumulated machine evidence, not another speculative hardening pass.
