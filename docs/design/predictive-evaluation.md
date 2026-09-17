# Predictive Semantic Evaluation (B Tier)

`ai-doc` separates predictive semantic judgment from static analysis and empirical agent execution. The B tier answers a narrow question: **given a baseline and a candidate instruction set, which one is more likely to be easier for an AI agent to interpret and follow correctly?**

B is optional evidence. It is not required for core `ai-doc` operation and it does not claim measured Claude, Codex, or other target-agent task success.

## Evidence Pyramid

```text
A0 deterministic static analysis
        |
A1 optional local semantic static analysis
        |
B  optional predictive LLM judgment
        |
C  empirical target-agent execution
```

A observes or classifies properties of documentation. B predicts likely instruction-following quality. C would execute a real target agent and observe outcomes; C is outside this module.

## Purpose

B exists for changes where deterministic or local semantic checks cannot fully answer questions such as:

- Is the candidate clearer than the baseline?
- Did shortening a rule make its scope less precise?
- Is instruction priority easier to infer?
- Did the candidate preserve the intended required and forbidden behavior?
- Does the candidate reduce conflicting interpretations?

These are comparative judgments, not static facts. The implementation therefore compares baseline and candidate directly instead of assigning a universal quality score to a document in isolation.

## Non-Goals

B does not:

- execute Claude, Codex, or another coding agent;
- measure empirical task-success rate;
- prove that a candidate improves production behavior;
- replace A-tier invariant or static safety checks;
- require semantic evaluation for normal core operation.

Any result from B should be read as **predictive semantic evidence**.

## Domain Contract

The stable domain vocabulary is owned by `ai-doc`, not by DeepEval or a specific model provider.

`PairwiseSemanticEvaluator` compares:

```text
baseline + candidate + evaluation scenarios
        -> PairwiseSemanticResult
```

A result contains:

- `engine`: which adapter produced the result;
- `overall`: normalized overall outcome;
- `dimensions`: one result per requested comparison dimension;
- `reason`: concise overall explanation when available;
- `raw_summary`: adapter-specific supplementary data that is not the stable semantic contract.

The normalized outcomes are:

- `candidate`: the candidate is predicted better;
- `baseline`: the baseline is predicted better;
- `equivalent`: no meaningful preference is established;
- `uncertain`: evidence is missing, mixed, unsupported, or too weak to choose.

Uncertainty is a first-class result, not an error disguised as a score.

## Comparison Dimensions

The current implementation compares seven dimensions:

1. **clarity** — which version is easier for an agent to understand accurately;
2. **ambiguity** — which version leaves fewer plausible unintended interpretations;
3. **scope precision** — which version defines applicability and boundaries more precisely;
4. **instruction hierarchy** — which version expresses priority between rules, defaults, and exceptions more clearly;
5. **actionability** — which version makes expected actions more directly executable;
6. **semantic requirement preservation** — which version better preserves required and forbidden behavior from the baseline;
7. **conflicting interpretation risk** — which version is less likely to support conflicting interpretations.

Each dimension returns its own outcome and textual evidence. The implementation does not compress these dimensions into a magic numeric quality score.

## DeepEval Adapter

When no provider-neutral semantic command is configured, explicit B-tier pairwise evaluation can use `DeepEvalEvaluator`.

The existing absolute DeepEval behavior remains separate:

```text
candidate (or baseline)
  -> G-Eval required/forbidden scenario gate
  -> EvaluationResult
```

The pairwise path uses DeepEval's arena-style comparison when the installed DeepEval API exposes `ArenaGEval`, `ArenaTestCase`, and `Contestant`:

```text
baseline contestant
candidate contestant
        -> ArenaGEval per dimension
        -> normalized PairwiseDimensionResult
```

Framework-specific winner objects and reasons are translated into the domain-owned outcomes above. If the installed DeepEval version does not expose the arena API, the pairwise adapter returns an `uncertain` result rather than inventing a comparison.

The current DeepEval adapter derives the overall outcome from dimension wins:

- more candidate wins -> `candidate`;
- more baseline wins -> `baseline`;
- tied dimensions with any uncertainty -> `uncertain`;
- otherwise -> `equivalent`.

This aggregation is intentionally simple and transparent; it is not an empirical success-rate estimate.

## Provider-Neutral Semantic Path

If `AI_DOC_SEMANTIC_COMMAND` is configured, B can reuse the existing semantic-provider stack instead of DeepEval.

`ProviderPairwiseSemanticEvaluator` invokes the provider-neutral operation:

```text
compare_pairwise
```

with:

- baseline documents;
- candidate documents;
- evaluation scenarios;
- the required dimension names;
- the allowed normalized outcomes;
- an `ai-doc`-owned comparison rubric.

The provider response is normalized into the same `PairwiseSemanticResult` contract. Missing dimensions are filled as `uncertain`. Unknown outcome strings also normalize to `uncertain` rather than silently becoming candidate wins.

The provider path shares the existing `BudgetedSemanticProvider`; it does not introduce a second budget or provider mechanism.

## Opt-In And Runtime Behavior

Pairwise B evaluation is disabled by default.

It can be enabled through configuration:

```yaml
optimization:
  pairwise_semantic: true
```

or explicitly on the CLI:

```bash
ai-doc optimize . --pairwise-semantic
```

Without pairwise semantic evaluation enabled, normal optimization does not need B-tier model calls.

If `AI_DOC_SEMANTIC_COMMAND` is configured, the pairwise evaluator uses the provider-neutral semantic command and its existing request/token/cost budget. Otherwise explicit pairwise evaluation uses the DeepEval path when available. The DeepEval path requires `optimization.deepeval_model`; without it, `ai-doc` reports a configuration error instead of allowing DeepEval to select an implicit provider or OpenAI model.

Important distinction: **default-off optionality is not the same as silent fallback after explicit opt-in.** If the user explicitly enables a DeepEval-backed path but the required DeepEval integration itself is unavailable or cannot be loaded, the current CLI may surface that as an execution error. Provider budget exhaustion, in contrast, is normalized into `uncertain` pairwise evidence.

## Interaction With A

A and B have different authority.

A-tier hard constraints continue to reject unsafe candidates independently of B. Pairwise semantic evidence does not override invariant regressions, static errors, or other rejection gates.

Conceptually:

```text
candidate
  -> A static/invariant gates
       -> rejected: stop
       -> viable: optional B comparison
                    -> recommendation evidence
```

Missing, equivalent, or uncertain pairwise evidence does not by itself block an otherwise eligible candidate.

The current recommendation policy also permits a positive pairwise result (`overall == candidate`) to count as a **material improvement** even when none of the numeric A/objective dimensions improved. This makes B more than decorative metadata: a candidate-predicted-better result may justify replacement, provided all existing reliability, clarity, invariant, evaluation, and rejection gates still pass.

That policy is deliberate implementation behavior and should be reviewed separately from the pairwise evaluator contract if the project later decides B should only confirm, rather than independently justify, a recommendation.

## Failure And Budget Semantics

The provider-neutral pairwise evaluator treats semantic budget exhaustion conservatively:

```text
budget exhausted
  -> PairwiseSemanticResult(overall=uncertain)
```

No candidate preference is manufactured when the evaluator cannot run.

Similarly, response normalization fills absent dimensions with explicit `uncertain` evidence and maps unknown outcome labels to `uncertain`.

DeepEval arena feature absence is also represented as uncertainty. A full DeepEval import/setup failure after explicit opt-in can currently surface through the CLI as an error rather than an uncertain result.

## Cost And Network Implications

Unlike A1 local ML, B generally implies an LLM-style evaluator or semantic-provider invocation and can therefore have network, token, latency, and monetary cost.

The provider-neutral path is protected by the existing semantic budgets:

- maximum requests;
- input-token budget;
- output-token budget;
- cost budget.

DeepEval follows the configured model and the provider behavior of the installed DeepEval environment. `ai-doc` requires that model to be named explicitly so enabling pairwise semantic evaluation cannot silently fall through to an implicit OpenAI default.

## Extension Points

The important extension boundary is the domain protocol:

```python
PairwiseSemanticEvaluator.compare_pairwise(
    baseline,
    candidate,
    suite,
) -> PairwiseSemanticResult
```

A future backend can implement this contract without changing recommendation or evidence schemas, provided it returns the normalized dimensions and outcomes.

Framework adapters should remain implementation details. `ai-doc` owns:

- comparison dimensions;
- outcome vocabulary;
- uncertainty semantics;
- claim boundary;
- evidence storage.

Backends own model/framework invocation.

## Model Dependence And Limitations

B is inherently model- and runtime-dependent.

A different evaluator model, provider version, rubric interpretation, temperature, or framework implementation may produce a different preference. The result is therefore not a timeless property of the documentation.

Additional limitations:

- pairwise judging can prefer fluent wording that does not improve real task execution;
- evaluators can miss repository-specific meanings or hidden context;
- scenario quality strongly affects judgment quality;
- the current overall DeepEval result uses a simple count of dimension winners rather than learned weighting;
- textual reasons are explanatory evidence, not formal proofs;
- a `candidate` result is a prediction, not a measured percentage increase in task success.

## Boundary To C

C would require actual target-agent execution under a controlled scenario:

```text
instruction variant
  + repository state
  + task
  + agent/model/version/tools/runtime
        -> actual execution
        -> observed success / violations / retries / cost
```

That evidence is contextual and empirical. It belongs to a separate research/benchmark layer.

B deliberately stops before that boundary. It predicts which instruction interface is likely better; it does not claim to have observed the target agent behaving better.
