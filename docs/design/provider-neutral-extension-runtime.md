# Provider-Neutral Extension Runtime

`ai-doc` separates runtime needs from provider implementations at the composition
boundary. Analyzer, evaluator, token-counter, recommendation-policy, and semantic-provider
capabilities use the same registry and process envelope.

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
        +-- SemanticProvider
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

Process adapters map internal domain objects into deliberate V1 wire DTOs before calling
the transport. They do not serialize the full `AiDocConfig`, full optimizer
`Candidate`, provider internals, or artifact paths as process contracts. Analyzer
payloads expose documents, profiles, token counts, graph relationships, and selected
analysis budget metadata. Recommendation payloads expose candidate summaries needed for
policy decisions, while core remains authoritative for eligibility and rejected-candidate
protection.

Process-backed capabilities reuse `ProcessTransport` and add thin capability adapters
instead of reimplementing subprocess and protocol handling.

The transport reports command-start failures, timeouts, non-zero exits, invalid JSON, protocol mismatches, mismatched request IDs, invalid envelope status, and explicit extension errors as infrastructure errors. The evaluator reports evaluator-result schema failures. Those failures are distinct from a valid negative evaluation.

## Provider Neutrality

Core code does not contain Claude, Codex, Gemini, or other provider conditionals. A logical evaluator such as `instruction-quality` can be backed by any executable selected in trusted project configuration.

Provider-specific SDKs, credentials, parsing, and retry behavior live inside the external adapter. The core only depends on the evaluator contract.

Core wraps selected semantic providers in `BudgetedSemanticProvider` at composition time.
Built-in, Python-extension, and process-extension providers all report usage through the
same `SemanticResponse.usage` path; budget exhaustion stops later semantic work in core
instead of relying on the extension to enforce limits.

## Acceptance Evidence

| Capability | L1 | L2 | L3 | L4 | Production test |
|---|---:|---:|---:|---:|---|
| Analyzer | yes | yes | yes | yes | L3: `test_project_extension_adds_finding_and_nested_check_discovers_root`; L4: `test_l4_process_analyzer_and_token_counter_affect_check` |
| Evaluator | yes | yes | yes | yes | L3: `test_l3_python_evaluator_affects_deep_check`; L4: `test_l4_process_evaluator_affects_deep_check` |
| Token counter | yes | yes | yes | yes | L3: `test_l3_python_token_counter_affects_static_report`; L4: `test_l4_process_analyzer_and_token_counter_affect_check`, `test_l4_process_token_counter_batches_repository_discovery` |
| Recommendation policy | yes | yes | yes | yes | L3: `test_l3_python_recommendation_policy_affects_optimize`; L4: `test_l4_process_recommendation_policy_affects_optimize` |
| Semantic provider | yes | yes | yes | yes | L3: `test_l3_python_provider_affects_semantic_generation_and_budgeting`; L4: `test_l4_process_provider_affects_semantic_generation` |

## Follow-Ups

Further extraction can add a deeper Policy Engine, richer tokenization metadata, separate
pricing and context-cost providers, more process transports, and additional optimizer
policy injection points. Runtime-specific loading models and custom document profiles
remain deferred.
