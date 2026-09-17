# Deferred Work

The following items are intentionally deferred.

Use this page to understand what is out of scope for the current release. Deferred items
are not rejected forever; they are postponed so the current tool remains small,
testable, and reliable.

If you want to start one of these items, first turn it into a design decision or issue
with scope, risks, and verification steps. Do not treat this list as permission to add a
large dependency or public contract without review.

## Evaluation And Optimization

- DSPy integration.
- Promptfoo dogfooding validation: determine whether Promptfoo produces useful findings
  or evaluation evidence beyond A0 and the other existing tiers, enough to justify its
  dependency and operational cost. If it mostly duplicates A0, consider deprecation in a
  separate decision.
- Vector databases, RAG infrastructure, and embeddings.
- Live provider-backed Tier 1 and Tier 2 semantic evaluation scheduling.
- Agent trace ingestion and task-frequency learning.
- Cross-file semantic duplication.
- Full graph restructuring across large documentation sets.
- Unsafe partial evaluation-cache inference.
- Provider rate-limit aware parallel evaluation.

## Extension Contracts

The current Extension API supports analyzer, evaluator, token-counter, recommendation
policy, and semantic-provider contracts through public API types, programmatic
registration, project-local Python extensions, and process extensions. These additional
extension contracts still need separate design before implementation:

- runtime-specific loading models;
- invariant detectors;
- candidate mutation strategies;
- custom document profiles.

## Runtime And Ecosystem

- Claude, Codex, and GitHub Copilot runtime-specific loaders.
- Persistent cross-repository learning.
- Generalized `.tools` package manager or dispatcher.
- SaaS backend or background optimization service.

## Reporting And CI

- HTML reporting.
- CI regression baselines.
- Automated GitHub Release publication.

## Packaging

- Cross-compilation for standalone executables.
- Bundling Promptfoo or Node into the standalone executable.
- Guaranteed DeepEval/GEPA packaged compatibility for every provider dependency.

## Pricing

- Dynamic model pricing retrieval.
- Monetary ROI claims without explicit workload and pricing data.
