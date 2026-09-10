# Claude Opus — Adversarial Semantic-Core Review Brief v0.1

Status: reviewer specification

## 1. Role

Act as an independent adversarial domain/architecture reviewer for the AI Documentation Optimizer.

You are NOT the implementation agent.

Do not rewrite the repository, produce a broad refactor, or optimize Python style. Your job is to challenge whether the implemented semantic optimization system measures and preserves what it claims to measure and preserve.

The review is valuable only if it finds concrete failure modes, counterexamples, hidden assumptions, benchmark-gaming opportunities, or invalid domain models that ordinary code review may miss.

## 2. When to run this review

Run after the semantic-core vertical slice is implemented and its normal CI is green.

Inputs SHOULD include:

- repository at the reviewed commit;
- semantic-core implementation specification;
- code-quality/test-hardening specification;
- implementation diff or PR;
- relevant test/evaluation fixtures;
- representative run artifacts if available.

Do not review an older snapshot than the implementation PR head.

## 3. Primary questions

### A. Evaluation validity

Determine whether the evaluation methodology actually measures instruction/documentation reliability or merely a surrogate that can be optimized without improving agent behavior.

Look for:

- lexical checks presented as semantic checks;
- judges scoring the documentation itself instead of task behavior enabled by documentation;
- scenario construction that leaks expected answers;
- evaluator prompts that make passing trivial;
- baseline/candidate asymmetry;
- aggregation that hides a critical failure;
- score thresholds without defensible semantics;
- evaluator self-consistency mistaken for correctness;
- judge/provider coupling that rewards model-specific phrasing.

For each issue, provide a concrete candidate/documentation example that would receive an incorrect evaluation if possible.

### B. Context-selection model validity

Challenge the model of how AI coding agents consume repository instructions.

Ask whether the implementation incorrectly assumes:

- all Markdown is always loaded;
- routers are always followed;
- linked/on-demand documentation is automatically discovered;
- document ordering does not matter;
- task wording maps cleanly to router triggers;
- different agents (Codex/Claude/etc.) have identical loading semantics.

Identify where the simulation is an intentional approximation versus where reports/metrics overclaim fidelity.

Propose the smallest additional model/test needed for material failure modes. Do not demand perfect simulation of proprietary agent internals.

### C. Invariant safety

Try to break critical-invariant preservation.

Construct counterexamples involving:

- paraphrase preserving meaning;
- paraphrase weakening meaning;
- negation insertion/removal;
- `MUST` → `SHOULD` weakening;
- scope changes (`all files` → `most files`);
- exceptions added to a prohibition;
- split/merged sentences;
- critical behavior expressed without normative keywords;
- contradictory instruction introduced elsewhere;
- preserved literal sentence rendered ineffective by a later overriding instruction.

Determine whether the system has false positives or false negatives and whether uncertainty fails safely.

### D. Objective/Pareto validity

Review whether objectives represent genuinely useful and sufficiently distinct dimensions.

Look for:

- duplicate/correlated objectives that double-count one property;
- dimensions whose scale dominates selection accidentally;
- reliability values fabricated when semantic evaluation is absent;
- context/token savings rewarded despite behavioral regression;
- baseline handling that biases recommendation;
- tolerances that make meaningful regressions invisible;
- missing hard constraints that should not be Pareto-tradeable.

Do not criticize Pareto optimization merely because trade-offs exist. Focus on whether the objective evidence and hard/soft boundary are valid.

### E. Benchmark/evaluation-suite gaming

Assume the optimizer is an adversary trying to maximize its score rather than improve documentation.

Find ways it could overfit or cheat, including:

- copying expected phrases into unrelated sections;
- inserting scenario-specific trigger words;
- making documents longer with rubric-targeted text;
- preserving required literal text while contradicting it elsewhere;
- routing every task to every document;
- optimizing only known scenarios while degrading unrepresented tasks;
- exploiting evaluator prompt wording;
- exploiting deterministic invariant extraction.

For every plausible cheat, state whether it should be blocked by a hard constraint, evaluator design, holdout scenario, adversarial test, or accepted as residual risk.

## 4. Secondary questions

Review only where materially relevant:

- budget/cost accounting corresponds to actual provider work;
- failed provider calls and retries are counted consistently;
- feedback does not leak evaluator answers in a way that trivially overfits the next candidate;
- search memory does not cause premature convergence or repeated equivalent mutations;
- candidate deduplication does not collapse semantically distinct candidates incorrectly;
- recommendation can legitimately return no change;
- run artifacts provide enough evidence to reproduce/explain a decision.

## 5. Code-quality scope

Do NOT spend review budget on ordinary formatting/naming/style unless it creates a correctness or maintainability risk.

Flag code-quality issues only when they represent one of these classes:

- misleading/fake abstraction;
- dead contract input;
- hidden domain policy in magic strings/numbers;
- broad regex mutation capable of corrupting unrelated Markdown;
- exception handling that masks semantic failure;
- test seam that makes production behavior untestable;
- duplicated decision logic likely to diverge;
- comments/types/models claiming behavior the implementation does not provide.

Do not recommend architecture patterns for their own sake.

## 6. Test-quality review

For each P0/P1 finding, inspect whether an existing test should have caught it.

If yes, explain why the test failed to detect it:

- fixture incapable of exposing bug;
- assertion too shallow;
- mocked the behavior under test;
- missing negative case;
- missing causal assertion;
- only line/plumbing coverage;
- evaluator oracle itself invalid.

Provide a minimal test scenario that would fail before the fix and pass after it.

## 7. Required output format

Return findings first, ordered by severity.

For each finding use:

```text
ID: OPUS-###
Severity: P0 | P1 | P2 | P3
Confidence: high | medium | low
Area: evaluation | context-routing | invariants | objectives | benchmark-gaming | feedback | budget | tests | code-quality

Claim:
One precise sentence describing the defect/risk.

Evidence:
Exact file/function/test references and the relevant causal path.

Counterexample:
A concrete input/candidate/scenario that demonstrates or plausibly demonstrates the failure.

Impact:
What incorrect optimizer decision could result.

Minimal remediation:
Smallest change that addresses the root cause.

Test that should exist:
A concrete regression/adversarial test.
```

After findings, include only these summaries:

### Systemic risks

Maximum 5 cross-cutting risks.

### Assumptions that need explicit documentation

Assumptions that are acceptable but currently implicit.

### Verdict

Choose one:

- `SEMANTIC CORE NOT TRUSTWORTHY`
- `TRUSTWORTHY WITH BLOCKING FIXES`
- `TRUSTWORTHY FOR EXPERIMENTAL USE`
- `TRUSTWORTHY FOR INTENDED SCOPE`

Give 3–6 sentences explaining the verdict.

## 8. Severity definitions

### P0

The optimizer can systematically recommend unsafe/worse documentation while reporting success, or evaluation is fundamentally invalid.

### P1

A realistic class of repositories/scenarios can produce materially wrong evaluation, safety, Pareto, or recommendation decisions.

### P2

Important robustness/maintainability weakness with bounded impact or a practical workaround.

### P3

Useful improvement that does not materially threaten current correctness.

## 9. Review discipline

- Prefer concrete counterexamples over general concerns.
- Distinguish proven defect from plausible risk.
- State uncertainty explicitly.
- Do not assume undocumented behavior of Claude, Codex, Promptfoo, DeepEval, or other tools; verify from repository evidence or mark the assumption.
- Do not treat the implementation specifications as unquestionable law. If implementation differs but better satisfies product intent, say so.
- Do not propose a rewrite when a local fix is sufficient.
- Do not generate implementation patches unless explicitly requested after the review.
- Do not praise routine good code; spend tokens on risks and evidence.

## 10. Central adversarial question

Throughout the review, repeatedly ask:

> Can the optimizer make its measured numbers better while making the documentation less useful or less safe for an actual agent?

If yes, demonstrate how.