# Semantic Optimization

This guide explains what `ai-doc optimize` currently does, how semantic evaluation fits into the search loop, what evidence the tool produces, and where the current implementation intentionally stops.

It is written for people operating or reviewing the tool. The implementation specification is deliberately more terse and forward-looking; this page describes the behavior that already exists.

## What Problem The Optimizer Solves

AI-facing documentation has two competing pressures.

First, important instructions must remain reliable. If a coding agent stops seeing a required validation rule, misses a router to detailed documentation, or interprets a MUST as optional guidance, saving a few hundred tokens is not an improvement.

Second, loading every detailed example and runbook into every agent request is expensive and noisy. Large always-loaded instruction files consume context even when most of their content is irrelevant to the current task.

The optimizer therefore does not ask only, “Can this Markdown be shorter?” It asks a broader question:

> Can this documentation become clearer and/or cheaper to load without losing behavior that an agent needs for real tasks?

That is why optimization combines static analysis, invariants, task-specific evaluation, context selection, Pareto comparison, feedback-directed repair, and an explicit baseline.

## The Mental Model

A run starts with the repository documentation as the **baseline**. The optimizer creates one or more **candidates** in an isolated output directory. Source Markdown is never edited in place.

Each candidate passes through a sequence of gates:

```text
baseline documentation
        |
        v
extract deterministic safety invariants
        |
        v
generate candidate mutation
        |
        v
Tier 0: local deterministic checks
        |
        +---- hard failure ----> reject candidate
        |
        v
optional semantic evaluation per scenario
        |
        +---- required behavior failure ----> reject / build feedback
        |
        v
build evidence-backed objective vector
        |
        v
compare candidate + baseline on Pareto frontier
        |
        v
optionally create repair children from failed candidates
        |
        v
recommend a candidate only when policy supports it
```

The important detail is causality. Semantic evaluation is not merely printed in a report: when configured, its result can reject a candidate and contributes to reliability. A failed evaluation can also become structured feedback used to create a child candidate.

## Baseline Is A Real Competitor

The optimizer is allowed to conclude that no generated change is better than the current documentation.

The baseline receives an objective vector and participates in Pareto comparison. This prevents a common optimizer failure mode where the tool assumes that because it generated a candidate, one of the candidates must be an improvement.

Recommendation is a separate decision from frontier membership. A candidate can be non-dominated and still fail the recommendation policy. If no candidate is sufficiently justified relative to baseline, the correct result is no recommended change.

## Tier 0: Cheap Checks First

Tier 0 is deliberately deterministic and local. Its job is to reject obviously unsafe or lower-quality candidates before an expensive semantic/model call is needed.

The current search path uses static analysis and invariant checks before semantic evaluation. Candidate fingerprints also help prevent duplicate work.

This ordering matters operationally. If a candidate deletes a literal critical invariant or introduces a blocking static regression, there is little value in paying a model to tell us that the candidate is bad.

Deterministic operations are recorded separately from external model requests. A completely local optimization run can therefore remain a zero-LLM-request run.

## Evaluation Scenarios

Repository-owned evaluation scenarios live under `.ai-doc/evals/`. Each scenario describes a task and may define required or forbidden behavior.

A conceptual example:

```yaml
id: migration
profile: coding
task: Change and validate a database migration.
expected:
  required:
    - read the migration examples before changing them
  forbidden:
    - skip validation
```

Scenarios are evaluated independently. Requirements from one scenario must not leak into another scenario.

This is particularly important when a repository contains unrelated workflows. A CSS task should not fail because a database-specific requirement was accidentally attached to every evaluation case.

## Lexical Versus Semantic Evaluation

Not every evaluator is semantic.

The Promptfoo `echo + contains/not-contains` path is intentionally treated as lexical/deterministic evidence. It is useful for exact assertions and adapter testing, but it does not prove that an agent would behave correctly.

DeepEval is the current semantic evaluation path exposed by `optimize --deep`. When deep evaluation is enabled, the CLI tells the operator that external model calls may occur.

The distinction is important because the optimizer must not manufacture a semantic reliability number from an unrelated deterministic heuristic. When no semantic evaluation exists, semantic reliability should be treated as unavailable rather than silently pretending that invariant recall means the same thing.

## Effective Context: The Evaluator Does Not Automatically Read Everything

A central design decision is that the repository documentation corpus is not the same thing as the context an agent receives for one task.

Consider this structure:

```text
AGENTS.md
  -> tells the agent when to read docs/database.md

docs/database.md
  -> detailed migration examples

docs/css.md
  -> CSS conventions
```

For a database migration task, the desired effective context may be:

```text
AGENTS.md + docs/database.md
```

rather than:

```text
AGENTS.md + docs/database.md + docs/css.md + every other Markdown file
```

The current context-selection boundary models this distinction. Instruction/skill documentation forms the always-loaded side; task-relevant reference documentation can be selected on demand. Semantic evaluation is then performed against the selected context for each scenario.

This makes context-cost optimization meaningful. A large examples section can move out of `AGENTS.md` into a reference document without automatically disappearing from every task that needs it.

### Current limitation

The selector is intentionally a deterministic approximation, not a perfect simulation of Claude, Codex, Copilot, or another coding agent. Keyword overlap and explicit references are used to approximate discoverability.

That means routing semantics remain an area to harden. In particular, future work must ensure that an optimizer cannot keep enough matching vocabulary to make the selector load a document while weakening the actual instruction that would cause a real agent to discover it.

## Deterministic Invariants

The optimizer extracts obvious normative statements such as rules containing MUST, NEVER, REQUIRED, or FORBIDDEN and checks that candidates do not simply lose them.

This is intentionally conservative. A cheap literal check is valuable because it catches dangerous transformations without a model call.

The code also has a semantic-verification boundary capable of representing:

- preserved;
- weakened;
- removed;
- uncertain.

Tests demonstrate that this boundary can accept a meaning-preserving paraphrase and reject a weakening. However, a concrete semantic invariant verifier is not yet wired into the normal CLI production path. The current production safety model should therefore be understood as stronger on explicit normative language than on implicit critical behavior.

That remaining work is tracked in the semantic-core specification.

## Candidate Generation

The current production optimizer has deterministic mutation strategies. These are useful even after semantic generation exists because they are cheap, reproducible, reviewable, and available offline.

Examples of useful deterministic transformations include removing duplication, extracting oversized detail, and strengthening a router after evaluation feedback identifies a weak route.

There is also a semantic candidate-generator boundary. It can receive search state such as previous candidate summaries, explored transformations, feedback, and memory. Tests prove that these inputs reach an injected semantic generator.

A production semantic generator is not yet wired into the normal CLI path. Therefore `balanced` and `search` should not yet be interpreted as “an LLM freely rewrites the documentation.” They currently perform bounded search over the implemented mutation mechanisms, with optional semantic evaluation when `--deep` is enabled.

## Feedback-Directed Repair

One of the most important completed parts of the semantic core is the repair loop.

A candidate can make a useful structural/context-cost change and still fail a behavioral scenario. Instead of throwing away the entire direction, the optimizer can turn the failure into structured feedback and create a child candidate.

The integration test exercises a concrete shape of this problem:

1. a large examples section is extracted from an always-loaded instruction document;
2. the resulting router is too weak for a semantic scenario;
3. semantic evaluation fails the parent;
4. feedback identifies the router weakness;
5. a child applies the router-strengthening repair;
6. the child is evaluated again;
7. the repaired child passes and can become the recommendation.

This is different from a test that manually creates a feedback object. The failure originates in the evaluator and causally affects the next candidate.

## Objective Vector And Pareto Frontier

The optimizer keeps several dimensions separate instead of collapsing everything into one weighted score.

The objective vector can contain:

- reliability;
- clarity;
- critical invariant recall;
- always-loaded tokens;
- expected task-context tokens;
- estimated context cost.

Pareto dominance means candidate A dominates candidate B only when A is no worse on every comparable objective and strictly better on at least one, after configured tolerances.

This matters because documentation optimization has genuine trade-offs. A candidate that saves many tokens but reduces reliability should not automatically win because somebody chose an arbitrary weight such as “tokens × 0.7 + reliability × 0.3.”

Missing semantic evidence is also different from a low semantic score. The model supports unavailable reliability rather than requiring a fabricated precise number.

## Search And Lineage

`conservative`, `balanced`, and `search` control how broadly candidates are explored.

`conservative` is intended for a small low-risk deterministic attempt. `balanced` generates competing candidates and compares them. `search` can continue for bounded generations and create children from previous candidates.

Candidates have IDs such as `C001`, parent IDs, generation numbers, strategies, proposals, objective vectors, evaluation results, costs, fingerprints, statuses, and rejection reasons.

The run writes lineage separately so a reviewer can reconstruct parent/child relationships without inferring them from directory names.

## Run Artifacts

A normal optimization run writes under:

```text
.ai-doc-output/<run-id>/
|-- run.json
|-- baseline/
|-- candidates/
|   `-- C001/
|       |-- proposal.json
|       |-- candidate/
|       |-- evaluation.json
|       `-- diff.patch
|-- frontier.json
|-- lineage.json
|-- search-memory.json
`-- report.json
```

These artifacts have different purposes.

`proposal.json` describes the candidate operations. `candidate/` contains the rendered documentation tree. `diff.patch` makes human review straightforward. `evaluation.json` records candidate evaluation when one ran. `frontier.json` records non-dominated candidates. `lineage.json` records parent relationships. `search-memory.json` captures accumulated search state. `run.json` and `report.json` provide the broader run/result view.

The artifact model is intentionally review-first: generation does not imply application.

### Current evidence limitation

The artifacts do not yet preserve every semantic decision needed for a complete forensic explanation. In particular, future work will persist the exact feedback used for a repair child, semantic invariant decisions, stronger recommendation/no-change reasoning, and complete provider token/USD telemetry.

## Request And Cost Accounting

The current domain model separates:

- deterministic operations;
- generation requests;
- evaluation requests;
- prompt-suboptimizer requests.

This fixes an important accounting problem: a regex transformation is not an LLM request and should not consume `max_llm_requests`.

Request-budget behavior is therefore meaningful today.

Token and USD accounting is less complete. Fields exist for generation/evaluation input/output tokens and total cost, but production adapters do not yet consistently populate all of them. Treat request counts as the stronger current signal; full token/USD FinOps enforcement remains part of the remaining semantic-core work.

## GEPA

GEPA is behind a prompt-suboptimizer boundary. It is not the outer documentation search algorithm.

Current behavior is deliberately truthful: enabling GEPA does not pretend that prompt optimization happened when no eligible prompt artifact is wired. The run reports that no eligible artifact was optimized and why.

This is safer than a decorative flag, but it is not the final integration. The remaining milestone work is to make enabled + eligible perform a real suboptimization and route its output through the normal safety, evaluation, budget, and Pareto machinery.

## Reading A Result As A Human

When reviewing an optimizer run, do not start with “Which candidate has the smallest token count?” A safer review order is:

1. Check whether the candidate was rejected and why.
2. Inspect semantic scenario failures/passes when deep evaluation ran.
3. Inspect invariant recall and safety-sensitive changes.
4. Read `diff.patch` and confirm that routing still makes sense to a human.
5. Compare always-loaded and expected-context cost with baseline.
6. Check whether the candidate is on the Pareto frontier.
7. Treat the recommendation as evidence-backed advice, not automatic permission to apply the patch.

The optimizer is designed to make this review easier, not to remove the reviewer from the loop.

## What Is Complete And What Is Not

The semantic core already has a real causal evaluation/repair loop, baseline-aware Pareto comparison, task-specific context selection, deterministic safety gates, truthful lexical-versus-semantic evaluator classification, and isolated review artifacts.

The milestone is not yet complete because several extension seams are not production capabilities yet: semantic candidate generation, semantic invariant discovery/verification, full token/USD telemetry, behaviorally effective GEPA, richer persisted semantic evidence, and adversarial hardening of context routing.

For the authoritative remaining implementation work, read [`../../specs/semantic-optimizer-core-v0.3.md`](../../specs/semantic-optimizer-core-v0.3.md).