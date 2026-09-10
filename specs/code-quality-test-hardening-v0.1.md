# AI Documentation Optimizer — Code Quality and Test Hardening Specification v0.1

Status: implementation complete

## 1. Purpose

The repository's current code quality is acceptable and does not justify a broad rewrite. The main engineering risk is subtler: code can look architecturally mature while contracts, tests, and abstractions overstate the behavior that actually exists.

This milestone hardens the weak areas without aesthetic refactoring.

Goals:

- remove AI-generated scaffolding that has no causal behavior;
- prevent fake/unused contract inputs;
- eliminate unexplained domain magic values and magic strings;
- improve tests from plumbing coverage toward behavioral/domain coverage;
- measure line/branch coverage without treating the percentage as the product goal;
- add adversarial and mutation-oriented tests around high-risk domain paths;
- keep existing clean/simple code simple.

## 2. Engineering principle

Do not refactor code merely because an AI wrote it.

A change is justified when it improves at least one of:

- correctness;
- truthful contracts;
- maintainability;
- observability;
- testability;
- domain clarity;
- removal of dead or misleading behavior.

Prefer deleting a fake abstraction over completing it speculatively. Prefer wiring an already-designed contract into real behavior when the semantic-core milestone requires it.

## 3. AI-code smells prohibited in production code

### 3.1 Fake contract inputs

A public/internal domain method MUST NOT accept meaningful-looking parameters and immediately discard them with patterns such as:

```python

del suite

del previous_summaries, explored_transformations, memory
```

If an argument is intentionally unused because an interface requires it, that fact MUST be explicit and narrowly scoped (for example an underscore-prefixed adapter argument or documented protocol compatibility). Domain/search APIs MUST NOT imply that feedback, memory, evaluation suites, budgets, or strategy inputs are active when they do not affect behavior.

### 3.2 Placeholder behavior behind mature names

Names such as `semantic`, `deep`, `adaptive`, `feedback-directed`, `reliability`, `cost`, or `budget` MUST correspond to actual behavior.

If an implementation is lexical, deterministic, heuristic, approximate, or estimated, its model/report/name MUST make that limitation discoverable.

### 3.3 Magic strings

Repeated or domain-significant strings MUST NOT be scattered through control flow.

Examples include:

- candidate statuses;
- stop reasons;
- evaluator/engine identifiers;
- optimization modes;
- severity values;
- artifact names used as protocol;
- metadata keys consumed across modules;
- special candidate IDs such as baseline identity;
- mutation/feedback direction tokens when they control behavior.

Use `StrEnum`, typed models, named constants, or a small domain value object where appropriate.

Do NOT extract every one-off user-facing message into a constant. The goal is domain clarity, not constant-file theatre.

### 3.4 Magic numbers

Unexplained numeric literals that encode domain policy MUST be named/configured.

Examples include:

- thresholds;
- confidence cutoffs;
- scoring weights;
- tolerances;
- retry/generation limits;
- token/cost heuristics;
- section-size extraction thresholds;
- similarity thresholds.

Obvious structural values (`0`, `1`, `-1`, simple indexes, empty defaults) do not require ceremonial constants.

### 3.5 Regex policy hidden in implementation

Regex-based mutations that encode product policy MUST have a named rule/strategy and focused tests. Broad textual rewrites such as changing normative words globally MUST prove that code blocks, quotations, examples, headings, links, and unrelated prose are not corrupted.

Prefer AST/Markdown-structure-aware transformations when a regex cannot provide that guarantee cheaply.

### 3.6 Speculative abstractions

Do not introduce a Protocol, service, factory, adapter, strategy, or model solely because a future implementation might need one.

An abstraction SHOULD have at least one of:

- two real implementations;
- a real external boundary;
- a testing seam around nondeterministic/external behavior;
- a domain boundary that materially improves dependency direction.

Existing abstractions that satisfy these purposes should remain.

### 3.7 Broad exception handling

Catching `Exception` is allowed only at intentional boundary layers where arbitrary plugin/provider failures must be normalized. Such catches MUST preserve cause and useful diagnostics. Core domain logic SHOULD catch specific exceptions.

### 3.8 Truthful comments and docstrings

Comments/docstrings MUST explain constraints, invariants, or non-obvious reasoning. Do not add prose that merely restates the code or claims capabilities not enforced by tests.

## 4. Static analysis and linting

The repository SHOULD strengthen Ruff incrementally rather than enable every rule family at once.

Required target configuration for production code:

- existing `E`, `F`, `I`, `UP`, `B`, `SIM`;
- `ARG` for unused arguments;
- `PLR2004` for magic-value comparisons;
- `RUF100` for unused `noqa` directives;
- selected exception-quality rules (`TRY` family) only after reviewing false positives;
- selected complexity rules only with explicit, conservative thresholds.

Ruff supports unused-argument checking through `ARG` and magic-value comparison checking through `PLR2004`; use per-file ignores where framework callbacks/tests legitimately need otherwise. See Ruff's rule documentation rather than inventing custom equivalents when an existing rule fits.

### 4.1 Per-file policy

Tests MAY ignore `PLR2004` where literal values are clearer assertions.

Adapters/callbacks MAY ignore a specific unused-argument rule when a third-party interface requires the signature. Prefer a local `# noqa: ARG...` with a short reason over a repository-wide ignore.

### 4.2 Custom semantic guard

Add a small AST-based quality check for production code that fails when a function/method parameter is explicitly deleted (`del parameter`) inside `src/ai_doc`, except for a documented allowlist of adapter compatibility cases.

Rationale: generic unused-argument linting does not reliably detect the misleading pattern where an API accepts a meaningful parameter and deliberately deletes it.

The guard MUST:

- parse Python using `ast`, not regex;
- report file, line, function, and parameter;
- support a narrow explicit allowlist if a third-party callback contract requires it;
- run in CI;
- have its own tests;
- remain small enough to audit easily.

Do not turn this script into a home-grown linter framework.

### 4.3 Type checking

Keep strict mypy.

Do not silence type errors with broad `Any`, `cast`, or `# type: ignore` merely to make CI green. Boundary casts for dynamically imported optional dependencies are acceptable when isolated and tested.

Unused-ignore detection MUST remain enabled.

## 5. Coverage instrumentation

Add `coverage.py`/`pytest-cov` to development dependencies and CI.

Measure at least:

- statement coverage;
- branch coverage;
- missing lines in CI output;
- XML or JSON artifact suitable for future tooling.

Initial repository-wide fail-under threshold SHOULD be conservative (recommended 80%) so coverage becomes a ratchet rather than a mass of low-value tests.

After the baseline is measured, raise the threshold only when meaningful tests justify it.

Coverage percentage MUST NOT be accepted as proof of domain correctness.

Critical modules SHOULD have stronger behavioral expectations than the global percentage, especially:

- optimizer search/orchestration;
- evaluator adapters;
- invariant safety;
- candidate generation/repair;
- recommendation/Pareto integration;
- budget/cost enforcement;
- context-selection/routing semantics once implemented.

## 6. Test design rules

### 6.1 Test behavior, not existence

Integration tests SHOULD NOT stop at assertions such as:

- command exited zero;
- JSON file exists;
- more than one candidate exists;
- a field is present.

Those assertions are useful smoke checks but MUST be paired with assertions about the domain result when the test claims optimizer correctness.

### 6.2 Fixtures must be capable of exposing the bug

A regression test is invalid if its fixture makes the bug observationally equivalent to correct behavior.

Examples:

- a DeepEval baseline test MUST contain non-empty baseline documentation and assert that content reaches the evaluator;
- a scenario-isolation test MUST contain at least two scenarios with incompatible/different expectations;
- a routing test MUST contain both relevant and irrelevant on-demand documents;
- an invariant rewrite test MUST change wording while preserving meaning.

### 6.3 Causal assertions

For high-risk workflows, assert that changing an input changes the expected downstream behavior.

Examples:

- removing a required scenario changes reliability/candidate status;
- changing feedback changes the child mutation;
- exhausting actual request budget prevents another provider call;
- weakening a critical invariant rejects a candidate;
- extracting documentation reduces always-loaded context but relevant task context can still retrieve it.

### 6.4 Negative and adversarial cases

Every important happy-path behavior SHOULD have at least one negative/adversarial counterpart.

Particularly important:

- semantic evaluator returns a plausible but wrong score;
- provider result is malformed/partial;
- duplicate candidate has different lineage;
- candidate improves token cost but breaks required behavior;
- candidate preserves literal words but changes meaning;
- candidate changes wording but preserves meaning;
- one evaluation scenario attempts to leak into another;
- router points to a valid file that is irrelevant to the task;
- budget is reached between generation and evaluation;
- optional provider dependency is absent;
- plugin raises an unexpected exception.

### 6.5 Avoid mock theatre

Mock external boundaries, not the implementation under test.

Prefer deterministic fake providers implementing the real provider/evaluator boundary over deep monkeypatch chains. A test SHOULD exercise as much real domain orchestration as possible without paid/network calls.

### 6.6 Test names describe guarantees

Names SHOULD state observable behavior and condition, not implementation method.

Prefer:

`test_candidate_is_rejected_when_required_behavior_regresses`

over:

`test_evaluate_candidate_calls_feedback_builder`.

## 7. Mutation testing / test strength

Introduce mutation testing after the semantic-core vertical slice is implemented.

Recommended scope: critical domain modules first, not the entire repository.

The mutation tool is implementation choice; `mutmut` or an equivalent maintained Python mutation-testing tool is acceptable.

Initial mutation targets SHOULD include:

- `optimizer/search.py`;
- `optimizer/invariants.py`;
- evaluator normalization/configuration;
- objective/recommendation decisions;
- budget guards.

The milestone does not require a repository-wide mutation score gate immediately.

Instead:

1. establish a baseline;
2. identify surviving mutations in critical decision paths;
3. add meaningful tests for those survivors;
4. later introduce a threshold if the signal is stable.

Do not add tests whose only purpose is killing harmless implementation-detail mutations.

## 8. Property/invariant-oriented tests

Where practical, add property-style tests (Hypothesis is optional, not mandatory) for stable invariants such as:

- Pareto dominance is irreflexive;
- equivalent objective vectors do not dominate each other;
- a candidate cannot pass a hard constraint when a critical invariant is known missing;
- budget counters never decrease;
- generated artifact paths remain under the run directory;
- extension paths cannot escape project root;
- normalization is deterministic;
- candidate fingerprints are stable for equivalent rendered content.

Use a property-testing dependency only if it makes these tests materially simpler.

## 9. Specific weak areas to harden

### 9.1 Evaluators

Add tests that detect:

- empty-baseline substitution;
- cross-scenario assertion leakage;
- forbidden behavior handling;
- malformed evaluator output;
- score/message normalization;
- semantic vs lexical evaluator classification.

### 9.2 Search orchestration

Replace/augment artifact-existence tests with domain assertions covering:

- baseline participation;
- candidate rejection reason;
- objective changes;
- frontier membership;
- recommendation/no-recommendation;
- feedback-derived child lineage;
- real provider request accounting.

### 9.3 Invariants

Test lexical and semantic preservation separately. Include paraphrases, negation changes, modal weakening (`MUST` → `SHOULD`), split/merged sentences, and critical behavior without explicit normative keywords.

### 9.4 Generators

Every deterministic transformation MUST have focused tests for unintended scope. For broad regex/text transforms, include Markdown code fences, inline code, quotations, links, headings, and examples.

If a generator accepts search memory, feedback, previous summaries, or explored transformations, add a test proving each active input can affect output. Otherwise remove the input until it is real.

### 9.5 Plugins/extensions

Current extension boundary is intentionally broad. Preserve it, but test path traversal, missing registration function, registration of invalid analyzer, plugin exception wrapping, and debug/non-debug diagnostics.

## 10. CI quality gates

CI SHOULD contain explicit named steps for:

1. Ruff lint;
2. custom AST contract guard;
3. strict mypy;
4. pytest with branch coverage;
5. coverage threshold;
6. existing packaging smoke;
7. existing CLI smoke.

Mutation testing MAY run separately/manual/nightly initially because it can be slower.

Do not make paid model calls in required CI.

## 11. Definition of Done

This milestone is complete when:

- production code contains no unexplained `del` of meaningful function parameters;
- unused argument and unused suppression checks are enforced;
- domain-significant magic strings are represented by typed/named domain values where appropriate;
- domain-significant magic numbers are named/configured;
- broad regex policy mutations have adversarial scope tests or are replaced by structured transformations;
- coverage with branches is measured in CI;
- a conservative fail-under threshold is enforced and documented;
- evaluator tests can expose the known baseline/scenario-isolation classes of bugs;
- search tests assert domain behavior, not only generated artifacts;
- critical paths have negative/adversarial cases;
- fake external providers are preferred over deep mocking;
- semantic-core tests demonstrate causal input → decision relationships;
- mutation testing has been run against critical optimizer/evaluator paths and surviving meaningful mutations are documented or killed with tests;
- strict mypy and cross-platform CI remain green;
- no broad cleanup/rewrite is performed solely for style.

## 12. Non-goals

This milestone does not require:

- 100% line coverage;
- 100% mutation score;
- rewriting all modules into a new architecture;
- extracting every string/number into a constant;
- banning regex entirely;
- banning `Any`/`cast` at dynamic third-party boundaries;
- enabling every Ruff/Pylint rule;
- adding abstractions solely to satisfy SOLID terminology;
- testing private implementation details that have no behavioral consequence.

## 13. Final constraint

The quality system must make misleading AI-generated code harder to merge, not merely make the repository look more formally engineered.

Every new lint rule, custom guard, coverage threshold, or test category MUST be justified by a defect class it can actually detect.

## 14. Completion record

Implementation evidence was recorded before merge on commit `1d557f1f82702a9123d7e4bbe2cc261d0439c506`.

- `ci`, `Pylint`, `Dependency compatibility`, and the focused `mutation-testing` workflow all completed successfully on that implementation commit.
- The final focused mutation baseline covered the configured critical optimizer/evaluator/provider paths and produced 1,876 mutants: 1,478 killed, 397 survived, and 1 reported with no tests. The mutation run, results command, and CI-stats export all exited successfully.
- Survivor review was representative across the critical categories rather than a claim that every one of the 397 residual mutants was manually classified. Meaningful survivors found during that review were converted into behavioral assertions for semantic-provider usage accounting, configured Pareto tolerances, Promptfoo fallback and full configuration contracts, and literal-invariant provenance/confidence/evidence.
- Residual survivors are retained as the v0.1 baseline. Representative residual classes are equivalent or low-signal implementation-detail mutations, defensive/diagnostic branches, and external-boundary details whose behavior is already covered at the contract level. This milestone intentionally does not introduce a 100% mutation target or repository-wide mutation-score gate; the baseline should be revisited before a future threshold is adopted.
- The mutation workflow preserves structured statistics, survivor listings, representative survivor diffs, stderr, and exit codes as CI artifacts so future mutation reviews are reproducible without making the full mutation suite a required score gate.

### AST guard allowlist disposition

No production callback or adapter currently requires deliberate deletion of a function parameter. Therefore v0.1 does not add an empty/speculative allowlist mechanism merely to satisfy a hypothetical future case. If a real third-party callback contract later requires such deletion, the guard must gain a narrow explicit exception together with a focused regression test. The conditional allowlist requirement was not activated by this milestone.

### DoD disposition

The v0.1 Definition of Done is satisfied by the implemented static checks, branch-coverage gate, behavioral/adversarial tests, focused mutation baseline and survivor review above, with strict/cross-platform CI green on the implementation commit. No broad aesthetic rewrite or mutation-score theatre was introduced.
