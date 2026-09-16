# Extension API

Project-local extensions let repositories add custom checks or named runtime components without forking `ai-doc`.

Use this page when the built-in analyzers or evaluators are not enough and your organization needs a repository-specific rule or provider adapter. If you only want to configure which files are analyzed, use [Configuration](configuration.md) instead.

`ai-doc` supports two extension shapes:

- in-process Python extensions loaded from trusted project files;
- process extensions launched through a portable JSON stdin/stdout protocol.

## Where Extensions Run

Extensions run when a command loads the analyzer or evaluation pipeline:

- `ai-doc check`
- `ai-doc check --deep`, before the optional deep evaluator runs
- `ai-doc optimize`, for baseline and candidate static gates
- `ai-doc optimize --deep`, where a configured evaluator can replace the built-in deep evaluator

Extensions do not currently extend `init`, `doctor`, `setup`, `version`, packaging/build behavior, or every optimizer policy. Deeper Policy Engine extraction, richer tokenization/pricing/context-cost providers, and additional transports remain follow-up work.

## Stability Contract

Stable imports live under:

```python
from ai_doc.api.v1 import AnalysisContext, Finding, FindingCategory, FindingSeverity
```

Process runtime helpers that are intended for programmatic composition are also exported
from `ai_doc.api.v1`:

```python
from ai_doc.api.v1 import PROTOCOL_VERSION, ProcessEvaluator, ProcessExtensionError, ProcessTransport
```

Anything outside `ai_doc.api.v1` should be treated as internal unless explicitly documented otherwise.

## In-Process Python Extensions

`.ai-doc.yaml`:

```yaml
extensions:
  - path: .ai-doc/extensions/custom_rules.py
```

Rules:

- paths are relative to the project root unless absolute;
- paths must stay inside the project root;
- extensions are loaded only when explicitly configured;
- extension code executes with normal Python privileges;
- do not configure untrusted extension files.

This example reports an informational finding whenever a document mentions generated files.

```python
from ai_doc.api.v1 import AnalysisContext, Finding, FindingCategory, FindingSeverity


class GeneratedFilesPolicy:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            if "generated files" in document.text.lower():
                findings.append(
                    Finding(
                        code="ORG_GENERATED_FILES_POLICY",
                        category=FindingCategory.RISK,
                        severity=FindingSeverity.INFO,
                        path=document.relative_path,
                        section=None,
                        message="Document mentions generated-file policy.",
                        evidence={"extension": "custom_rules.py"},
                        suggestion=None,
                    )
                )
        return findings


def register(registry) -> None:
    registry.add_analyzer(GeneratedFilesPolicy())
```

Extensions must define:

```python
def register(registry) -> None:
    ...
```

The registry validates registrations. Existing analyzer extensions keep using `registry.add_analyzer(...)` unchanged. The registry also supports named evaluators, token counters, recommendation policies, and providers for composition-boundary dependency injection.

## Process Evaluator Extensions

Process evaluator extensions are provider-neutral. A logical evaluator name such as `instruction-quality` can be backed by Claude, Codex, Gemini, a local model, a rules engine, or any executable that speaks the protocol. Core code only sees the evaluator abstraction.

Inside `ai-doc`, the process runtime is split into a generic `ProcessTransport` and a capability-specific `ProcessEvaluator`. The transport owns process execution and the `ai-doc.extension/v1` envelope. The evaluator owns only the `evaluate` payload and `EvaluationResult` validation.

`.ai-doc.yaml`:

```yaml
evaluation:
  deep:
    evaluator: instruction-quality
extension_runtime:
  evaluators:
    instruction-quality:
      type: command
      command: [python, examples/extensions/simple_evaluator.py]
      timeout: 120
```

Commands are argv arrays and run with `shell=False`. stdout is reserved for protocol JSON. stderr is reserved for diagnostics and may be surfaced on failures.

### Request

The process receives one JSON object on stdin:

```json
{
  "protocol": "ai-doc.extension/v1",
  "operation": "evaluate",
  "request_id": "opaque-request-id",
  "payload": {
    "baseline": {"root": ".", "total_tokens": 10, "documents": []},
    "candidate": null,
    "suite": {"scenarios": []}
  }
}
```

### Successful Response

```json
{
  "protocol": "ai-doc.extension/v1",
  "request_id": "same-request-id",
  "status": "ok",
  "result": {
    "engine": "custom-evaluator",
    "passed": true,
    "cases": []
  }
}
```

### Error Response

```json
{
  "protocol": "ai-doc.extension/v1",
  "request_id": "same-request-id",
  "status": "error",
  "error": {"code": "unavailable", "message": "provider unavailable"}
}
```

`ai-doc` treats command-start failures, timeouts, non-zero exits, invalid JSON, unsupported protocol versions, mismatched request IDs, schema validation failures, and explicit extension errors as infrastructure errors. These are distinct from a valid negative evaluation result.

## Security

Both Python extensions and process extensions are trusted project configuration. Documentation content must not choose executables. Configure commands deliberately, avoid logging secrets, and pass provider credentials through the external adapter's trusted environment or config. The process runtime is a protocol boundary, not a sandbox.

## Failure Behavior

Normal mode reports concise diagnostics:

```text
Failed to load extension:
.ai-doc/extensions/custom_rules.py

Reason:
Analyzer registration must provide an object with analyze(context).
```

Debug mode includes stack details where supported.
