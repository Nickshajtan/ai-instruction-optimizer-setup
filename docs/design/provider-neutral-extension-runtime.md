# Provider-Neutral Extension Runtime

`ai-doc` separates runtime needs from provider implementations at the composition boundary.

```text
CLI / composition root
        |
        v
ExtensionRegistry
        |
        +-- Analyzer
        +-- Evaluator
        +-- TokenCounter
        +-- RecommendationPolicy
        +-- LLMProvider
```

Business logic receives selected dependencies through constructors or function arguments. It does not resolve providers from a global registry. The registry validates and names implementations at the composition boundary.

## Extension Shapes

In-process Python extensions remain the compatibility path. Existing extensions that define `register(registry)` and call `registry.add_analyzer(...)` continue to work.

Process extensions are the portable ABI. A process evaluator receives a versioned `ai-doc.extension/v1` JSON request on stdin and returns JSON on stdout. stderr is reserved for diagnostics.

The process adapter reports command-start failures, timeouts, non-zero exits, invalid JSON, protocol mismatches, schema failures, mismatched request IDs, and explicit extension errors as infrastructure errors. Those failures are distinct from a valid negative evaluation.

## Provider Neutrality

Core code does not contain Claude, Codex, Gemini, or other provider conditionals. A logical evaluator such as `instruction-quality` can be backed by any executable selected in trusted project configuration.

Provider-specific SDKs, credentials, parsing, and retry behavior live inside the external adapter. The core only depends on the evaluator contract.

## Follow-Ups

Further extraction can add a deeper Policy Engine, richer tokenization metadata, separate pricing and context-cost providers, more process transports, and additional optimizer policy injection points.
