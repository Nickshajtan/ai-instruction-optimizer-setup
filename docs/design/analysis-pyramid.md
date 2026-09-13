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
- stronger semantic-duplicate evidence through bidirectional NLI entailment;
- semantic contradiction through a local natural-language-inference (NLI) classifier.

A1 is optional. Install the Python integration with:

```bash
python -m pip install "ai-doc[ml]"
```

`pip` installs the Python runtime dependencies, not every configured model artifact. Model weights are deliberately a separate deployment concern. They may be supplied as explicit local directories, through `AI_DOC_MODEL_ROOT`, from an already-populated local Hugging Face / sentence-transformers cache, or embedded into a standalone executable at build time.

Normal `ai-doc check` execution must not silently download model artifacts. The concrete adapters always use local-only loading. Once runtime dependencies and model artifacts are available locally, inference runs against only the text spans supplied by `ai-doc` and does not require an external inference API.

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

The model fields can also contain explicit local directory paths instead of registry-style names.

For a shared local bundle:

```text
models/
|-- similarity/
`-- nli/
```

set:

```bash
export AI_DOC_MODEL_ROOT=/path/to/models
```

For a fully offline standalone artifact, the same bundle can be embedded at build time:

```bash
python -m tools.build executable --extras ml --model-root /path/to/models
```

That executable includes the ML runtime and both model directories, so the target machine does not need Python, a pre-populated Hugging Face cache, or network access. See [Packaging](../operations/packaging.md) for the complete model-resolution order and deployment options.

If A1 is disabled or unavailable, A0 continues to work normally.

## Why Local ML Still Belongs To A

The boundary is based on the claim being made, not merely on whether machine learning is involved.

A local embedding model can say that two passages are semantically similar. A local NLI classifier can say that one supplied statement likely entails, contradicts, or is neutral toward another supplied statement. These are properties or probabilistic relationships of the supplied text.

They do **not** establish that a particular target model will follow the instructions better. That stronger claim belongs to B or C.

## Semantic Duplication Evidence

Embedding similarity is a candidate-generation signal, not proof of equivalence.

The A1 duplication pipeline is:

```text
text spans
  -> embedding similarity
  -> candidate pair above similarity threshold
  -> NLI: A entails B
  -> NLI: B entails A
  -> strong semantic-duplicate evidence
```

If the embedding similarity threshold is met but bidirectional entailment is not established with sufficient confidence, `ai-doc` reports only a probable semantic duplicate based on similarity. A pair is promoted to a strong semantic duplicate only when both NLI directions are `entailment` and both satisfy the configured NLI confidence threshold.

This distinction matters because one-way entailment is usually closer to redundancy, specialization, or scope narrowing than true equivalence. A confident contradiction is excluded from duplicate findings.

Even bidirectional NLI entailment is probabilistic evidence, not a mathematical proof that two repository instructions are perfectly interchangeable.

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
- bidirectional entailment is stronger duplicate evidence than similarity alone, but is still probabilistic;
- confidence thresholds are explicit and configurable;
- users should review semantic findings instead of treating them as formal proofs.

## Extension Architecture

Analyzers own domain meaning. Shared ML infrastructure only provides narrow capabilities.

```text
SemanticDuplicationAnalyzer
    -> SemanticSimilarityEngine
    -> NLIEngine

SemanticContradictionAnalyzer
    -> NLIEngine
```

The concrete sentence-transformers adapters are implementation details. Tests and future integrations can inject alternative engines without changing analyzer semantics.

This boundary also permits future local implementations, quantized models, ONNX backends, or organization-specific classifiers without turning each analyzer into an ML integration module.

One-way entailment may later support a dedicated redundancy or scope-relation analyzer, but it should not be mislabeled as equivalence.

## Model Provisioning Is Part Of The A1 Contract

A1 is local by design, so model distribution cannot be left implicit. The runtime must never depend on a target machine being able to reach a public model registry.

Supported patterns are:

- explicit local model directories in configuration;
- a shared `AI_DOC_MODEL_ROOT` containing `similarity/` and `nli/`;
- an already-populated local model cache;
- a standalone executable built with `--extras ml --model-root ...`, which embeds both model directories.

The last option creates the strongest offline guarantee: runtime + model weights are one build artifact. The trade-off is artifact size and model-version coupling.

Model licensing/redistribution terms still apply. A technically self-contained executable is not automatically legally redistributable.

## Scaling

Exact A0 checks are cheap. Pairwise semantic analysis can grow quadratically with the number of candidate spans or rules.

For small instruction files, direct local NLI comparison can be acceptable. For larger repositories, embeddings act as a candidate-selection stage:

```text
text spans
  -> embeddings
  -> nearest / sufficiently similar candidate pairs
  -> NLI or analyzer-specific relation check
```

This is an optimization, not a semantic shortcut: high embedding similarity alone must never be promoted to a contradiction or strong-equivalence finding.

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
- Bidirectional NLI entailment is stronger semantic-equivalence evidence but remains probabilistic.
- NLI is a probabilistic classifier and may misunderstand repository-specific terminology or scope.
- A1 inference only sees the text supplied to it; it does not automatically know repository context that was not included in the compared spans.
- Installing `sentence-transformers` alone does not provide every configured model; model weights must be provisioned or embedded explicitly.
- Local model size and runtime requirements can be substantial, which is why A1 is not a core dependency.
- Fully embedded offline binaries are larger and tied to the model versions packaged at build time.
- Pairwise semantic analysis can become expensive on large repositories and may require candidate filtering.
- Neither A0 nor A1 proves improvement in real agent task success.
