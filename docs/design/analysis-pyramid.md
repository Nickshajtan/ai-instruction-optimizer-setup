# Analysis Pyramid

`ai-doc` separates evidence by how strongly it depends on models and runtime behavior. The purpose of this split is to keep ordinary repository analysis cheap, reproducible, and honest about what each signal can prove.

## A: Static Analysis

A produces observations about the documentation itself. It never claims that Claude, Codex, or another target agent actually performed better.

### A0: Deterministic Static Analysis

A0 uses deterministic logic such as parsing, normalization, token estimates, exact matching, regexes, and structural rules. It requires no model artifacts and no network access.

Examples:

- exact paragraph and list-item duplication;
- literal normative contradictions such as `Always validate changes` versus `Never validate changes`;
- token and context-cost estimates;
- structure and clarity heuristics;
- literal invariant preservation.

A0 is the baseline capability of `ai-doc` and must remain available in the core installation.

### A1: Local Semantic Static Analysis

A1 adds local pretrained ML models to classify relationships between text spans. It is still static analysis because the model inspects documentation only; it does not execute the target coding agent or predict a measured task-success rate.

The initial A1 capabilities are:

- semantic duplication through sentence embeddings and similarity;
- semantic contradiction through a local natural-language-inference (NLI) classifier.

A1 is optional. Install the Python integration with:

```bash
python -m pip install "ai-doc[ml]"
```

Model weights are not bundled into the core package. They must already exist in the local model cache before A1 runs. Normal `ai-doc check` execution must not silently download model artifacts. Once dependencies and model artifacts are available locally, inference can run without an external inference API.

Example configuration:

```yaml
local_ml:
  enabled: true
  semantic_duplication: true
  semantic_contradiction: true
  similarity_model: sentence-transformers/all-MiniLM-L6-v2
  nli_model: cross-encoder/nli-deberta-v3-small
  similarity_threshold: 0.90
  nli_confidence_threshold: 0.90
```

If A1 is disabled or unavailable, A0 continues to work normally.

## Why Local ML Still Belongs To A

The boundary is based on the claim being made, not merely on whether machine learning is involved.

A local embedding model can say that two passages are semantically similar. A local NLI classifier can say that two statements are likely contradictory. These are properties or probabilistic relationships of the supplied text.

They do **not** establish that a particular target model will follow the instructions better. That stronger claim belongs to B or C.

## Similarity Is Not Contradiction

Semantic similarity is useful for finding candidate duplicates and for reducing the number of pairs that need deeper inspection. It is not evidence of contradiction.

For example, these statements should have high similarity:

```text
Run tests before committing.
Do not run tests before committing.
```

Yet their relationship is contradictory. `ai-doc` therefore does not infer contradiction from cosine similarity. Contradiction is delegated to the NLI relation classifier.

## NLI Is Probabilistic

NLI models typically classify a pair of statements as entailment, contradiction, or neutral and expose a confidence value. That classifier can be wrong.

For that reason:

- literal A0 contradictions can be reported as deterministic errors;
- A1 NLI contradictions should be reported as probabilistic findings;
- confidence thresholds are explicit and configurable;
- users should review semantic findings instead of treating them as formal proofs.

## Extension Architecture

Analyzers own domain meaning. Shared ML infrastructure only provides narrow capabilities.

```text
DuplicationAnalyzer
    -> SemanticSimilarityEngine

ContradictionAnalyzer
    -> NLIEngine
```

The concrete sentence-transformers adapters are implementation details. Tests and future integrations can inject alternative engines without changing analyzer semantics.

This boundary also permits future local implementations, quantized models, ONNX backends, or organization-specific classifiers without turning each analyzer into an ML integration module.

Potential future semantic relations include bidirectional entailment for stronger duplicate/equivalence evidence and one-way entailment for redundancy or scope relationships. These should be added only when they support a concrete analyzer use case.

## Scaling

Exact A0 checks are cheap. Pairwise semantic analysis can grow quadratically with the number of candidate spans or rules.

For small instruction files, direct local NLI comparison can be acceptable. For larger repositories, embeddings can act as a candidate-selection stage:

```text
text spans
  -> embeddings
  -> nearest / sufficiently similar candidate pairs
  -> NLI or analyzer-specific relation check
```

This is an optimization, not a semantic shortcut: high embedding similarity alone must never be promoted to a contradiction finding.

## False Positives And False Negatives

A0 contradiction detection intentionally prefers false negatives over guessing semantic equivalence. It catches only relationships that can be justified by deterministic normalization and rule polarity.

A1 increases recall but introduces probabilistic false positives and model-specific behavior. Thresholds should therefore be calibrated against a fixture corpus rather than treated as universal constants.

## Boundary To B And C

The evidence pyramid is:

```text
A0 deterministic static
        |
A1 local semantic static
        |
B  predictive LLM judgment
        |
C  empirical target-agent execution
```

B asks questions such as whether a candidate instruction set is likely clearer, less ambiguous, better scoped, or easier for an AI agent to follow. It may use DeepEval or the provider-neutral semantic evaluation layer and remains optional.

C measures actual outcomes by executing a real target agent under a controlled task/repository/runtime configuration. It is contextual empirical evidence, not a normal static check.

A therefore provides cheap facts, heuristics, and semantic proxies. B provides predictive judgment. C provides observed target-agent outcomes.

## Limitations

- Embedding similarity does not prove semantic equivalence.
- NLI is a probabilistic classifier and may misunderstand repository-specific terminology or scope.
- A1 requires local model artifacts; installing `sentence-transformers` alone does not provide every configured model.
- Local model size and runtime requirements can be substantial, which is why A1 is not a core dependency.
- Pairwise semantic analysis can become expensive on large repositories and may require candidate filtering.
- Neither A0 nor A1 proves improvement in real agent task success.
