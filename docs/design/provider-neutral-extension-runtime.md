# Provider-Neutral Extension Runtime

`ai-doc` separates runtime needs from provider implementations at the composition
boundary. This page describes internal composition and the currently exposed
process-evaluator runtime; not every registry slot is a supported project extension
contract.

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

Process extensions are the portable ABI. `ProcessTransport` sends a versioned `ai-doc.extension/v1` JSON request on stdin and reads protocol JSON from stdout. stderr is reserved for diagnostics.

The portable runtime is layered:

```text
Domain capability
      |
Process adapter
      |
ProcessTransport
      |
ai-doc.extension/v1
      |
external executable
```

`ProcessTransport` owns execution and protocol mechanics: argv execution with `shell=False`, environment overlay handling, timeout, request ID generation, stdout parsing, protocol envelope validation, extension error responses, and stderr diagnostics. It accepts an operation name plus payload, so it is not evaluator-specific.

`ProcessEvaluator` is the evaluator-specific adapter. It maps documentation snapshots and evaluation suites into an `evaluate` payload, delegates to `ProcessTransport`, and validates the returned result as an `EvaluationResult`.

Future process-backed capabilities should reuse `ProcessTransport` and add their own thin
capability adapter instead of reimplementing subprocess and protocol handling. They still
need a documented configuration path and stability contract before becoming supported
project extensions.

The transport reports command-start failures, timeouts, non-zero exits, invalid JSON, protocol mismatches, mismatched request IDs, invalid envelope status, and explicit extension errors as infrastructure errors. The evaluator reports evaluator-result schema failures. Those failures are distinct from a valid negative evaluation.

## Provider Neutrality

Core code does not contain Claude, Codex, Gemini, or other provider conditionals. A logical evaluator such as `instruction-quality` can be backed by any executable selected in trusted project configuration.

Provider-specific SDKs, credentials, parsing, and retry behavior live inside the external adapter. The core only depends on the evaluator contract.

## Follow-Ups

Further extraction can add a deeper Policy Engine, richer tokenization metadata, separate
pricing and context-cost providers, more process transports, and additional optimizer
policy injection points. Recommendation-policy, token/loading-model, and provider
extension contracts remain deferred until designed explicitly.
