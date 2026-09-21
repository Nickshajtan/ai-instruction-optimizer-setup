# Extension API

Project-local extensions let repositories add custom checks or named runtime components without forking `ai-doc`.

Use this page when the built-in analyzers, token counter, evaluators, recommendation
policy, or semantic provider are not enough and your organization needs a
repository-specific implementation. If you only want to configure which files are
analyzed, use [Configuration](configuration.md) instead.

`ai-doc` supports two extension shapes:

- in-process Python extensions loaded from trusted project files;
- process extensions launched through a portable JSON stdin/stdout protocol.

## Where Extensions Run

Extensions run when a command loads the analyzer or evaluation pipeline:

- `ai-doc check`
- `ai-doc check --deep`, before the optional deep evaluator runs
- `ai-doc optimize`, for baseline and candidate static gates
- `ai-doc optimize --deep`, where a configured evaluator can replace the built-in deep evaluator

Extensions do not currently extend `init`, `doctor`, `setup`, `version`, packaging/build
behavior, runtime-specific loading models, pricing models, custom document profiles, or
candidate mutation strategies.

## Stability Contract

Stable imports live under:

```python
from ai_doc.api.v1 import AnalysisContext, Finding, FindingAdapter, FindingCategory, FindingSeverity
```

Process runtime helpers are also exported from `ai_doc.api.v1`:

```python
from ai_doc.api.v1 import PROTOCOL_VERSION, ProcessEvaluator, ProcessExtensionError, ProcessTransport
```

Anything outside `ai_doc.api.v1` should be treated as internal unless explicitly documented otherwise.

Export from `ai_doc.api.v1` does not automatically mean a component is configurable from
`.ai-doc.yaml`, process-backed, dynamically loadable as a project extension, or stable in
every possible composition role. Extension support is described in four levels:

| Level | Meaning |
|---|---|
| L1 public API | Stable public Python types exported from `ai_doc.api.v1`. |
| L2 programmatic DI | Components can be registered and resolved through `ExtensionRegistry`. |
| L3 project extension | A configured Python extension can register and select the component for a real CLI path. |
| L4 process extension | A configured command can implement the component through `ai-doc.extension/v1`. |

Current capability matrix:

| Capability | L1 | L2 | L3 Python | L4 process | Production path |
|---|---:|---:|---:|---:|---|
| Analyzer | yes | yes | yes | yes | `check`, optimizer static gates |
| Finding adapter | yes | yes | yes | no | post-process static findings |
| Evaluator | yes | yes | yes | yes | `check --deep`, `optimize --deep` |
| Token counter | yes | yes | yes | yes | discovery, reports, FinOps, optimization snapshots |
| Recommendation policy | yes | yes | yes | yes | optimizer final recommendation |
| Semantic provider | yes | yes | yes | yes | semantic generation, invariants, evaluation, pairwise, GEPA |

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

The registry validates registrations. Existing analyzer extensions keep using
`registry.add_analyzer(...)` unchanged.

The registry also has named evaluator, token-counter, recommendation-policy, and provider
slots. Registering a named capability makes it available; the project still must select
that implementation through configuration before it affects production behavior.
Analyzers produce findings. Finding adapters transform the resulting finding collection.
Built-in analyzers, Python extension analyzers, and configured process analyzers all run
in the same static analysis pass before adapters run. Register pure adapters with
`registry.add_finding_adapter(...)`; adapters compose in registration order, where each
adapter receives the previous adapter's output.

### Project-Specific Finding Adaptation

Use `adapt_findings` when the built-in heuristic is generally useful but a repository has
local semantics the core package should not hard-code. For example, an instruction file
may contain an `Architecture` section that is intentionally descriptive, while other
sections in the same file should still receive normal clarity findings.

```python
from ai_doc.api.v1 import AnalysisContext, Finding, FindingAdapter


class ProjectClarityAdapter(FindingAdapter):
    reference_sections = {"Architecture", "Project Context"}

    def adapt_findings(self, context: AnalysisContext, findings: list[Finding]) -> list[Finding]:
        return [
            finding
            for finding in findings
            if not (
                finding.code == "CLARITY_NO_ACTIONABLE_CONTENT"
                and finding.section in self.reference_sections
            )
        ]


def register(registry) -> None:
    registry.add_finding_adapter(ProjectClarityAdapter())
```

This pattern preserves the built-in analyzers, removes only the project-specific false
positive, and uses only public `ai_doc.api.v1` types. An object may implement both
`analyze(...)` and `adapt_findings(...)`; register it as both only when it should both
produce and transform findings. For backward compatibility, analyzer objects registered
with `registry.add_analyzer(...)` that also implement `adapt_findings(...)` are adapted
once. Project-specific policy belongs here when it would otherwise require
organization-specific heading names or workflow assumptions in `ai-doc` core.

Token counters may expose an `accuracy` attribute using `TokenCountAccuracy.EXACT`,
`TokenCountAccuracy.ESTIMATED`, `TokenCountAccuracy.MIXED`, or a matching string. If an
extension does not declare accuracy, reports mark the counter accuracy as `unknown`.

Example:

```python
def register(registry) -> None:
    registry.add_analyzer(CustomAnalyzer())
    registry.add_token_counter("company", CompanyTokenCounter())
    registry.add_evaluator("company", CompanyEvaluator())
    registry.add_recommendation_policy("company", CompanyPolicy())
    registry.add_provider("company", CompanySemanticProvider())
```

Then select the named components:

```yaml
components:
  token_counter: company
  recommendation_policy: company
  provider: company
evaluation:
  deep:
    evaluator: company
```

## Process Extensions

Process extensions are provider-neutral. A logical component name can be backed by
Claude, Codex, Gemini, a local model, a rules engine, or any executable that speaks the
protocol. Core code only sees the selected capability abstraction.

Inside `ai-doc`, the process runtime is split into a generic `ProcessTransport` and
capability-specific adapters such as `ProcessAnalyzer`, `ProcessEvaluator`,
`ProcessTokenCounter`, `ProcessRecommendationPolicy`, and `ProcessSemanticProvider`. The
transport owns process execution and the `ai-doc.extension/v1` envelope. Capability
adapters own their operation payloads and result validation.

`.ai-doc.yaml`:

```yaml
evaluation:
  deep:
    evaluator: instruction-quality
extension_runtime:
  analyzers:
    company-analyzer:
      type: command
      command: [python, examples/extensions/company.py]
  evaluators:
    instruction-quality:
      type: command
      command: [python, examples/extensions/simple_evaluator.py]
      timeout: 120
  token_counters:
    company-counter:
      type: command
      command: [python, examples/extensions/company.py]
  recommendation_policies:
    company-policy:
      type: command
      command: [python, examples/extensions/company.py]
  providers:
    company-provider:
      type: command
      command: [python, examples/extensions/company.py]
components:
  token_counter: company-counter
  recommendation_policy: company-policy
  provider: company-provider
```

Commands are argv arrays and run with `shell=False`. stdout is reserved for protocol JSON. stderr is reserved for diagnostics and may be surfaced on failures.

### Envelope

Every process operation receives one JSON object on stdin:

```json
{
  "protocol": "ai-doc.extension/v1",
  "operation": "...",
  "request_id": "opaque-request-id",
  "payload": {}
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

The protocol envelope version (`ai-doc.extension/v1`), operation name, and payload schema
version are separate compatibility concepts. Each capability payload includes
`"payload_version": 1`. Capability results also include `"payload_version": 1`; adapters
validate it before mapping process JSON back into domain objects.

Current operations:

| Operation | Payload v1 | Result |
|---|---|---|
| `analyze` | `payload_version`, document text/profile/token counts, link graph, and selected analysis budget metadata | `{"payload_version": 1, "findings": [...]}` |
| `evaluate` | `payload_version`, baseline snapshot, optional candidate snapshot, and evaluation suite v1 scenarios | `{"payload_version": 1, "engine": "...", "passed": true, "cases": [], "raw_summary": {}}`; `engine` may be omitted to use the configured process name |
| `count_tokens` | `payload_version`, optional `model`, and `items` with `id` and `text` | `{"payload_version": 1, "counts": {"item-id": 123}}` |
| `recommend` | `payload_version`, `baseline_id`, and eligible candidate summaries containing ids, status, objective vector, cost, rejection reasons, and limited evidence | `{"payload_version": 1, "candidate_id": "C001", "reason": "..."}` or `candidate_id: null` |
| `complete` | `payload_version`, stable semantic `operation`, and JSON-compatible `payload` | `{"payload_version": 1, "data": {}, "usage": {...}}` |

`ProcessTransport.describe()` can query the optional `describe` operation for a lightweight
manifest of supported capabilities. In v1 this is introspection only: `ai-doc` does not
call `describe` to validate configured capability support before production execution.
Existing commands remain compatible if they do not implement `describe`; selected
operations still fail explicitly if the process returns an error or invalid result.

`ai-doc` treats command-start failures, timeouts, non-zero exits, invalid JSON,
unsupported protocol versions, mismatched request IDs, schema validation failures, and
explicit extension errors as infrastructure errors. These are distinct from a valid
negative evaluation result. For `check`, `optimize`, `probe`, and `execute`, process
extension infrastructure failures report concise diagnostics and exit `1`; normal mode
does not print a Python traceback.

## Security

Both Python extensions and process extensions are trusted project configuration. Python
extensions execute arbitrary in-process code. Process extensions execute arbitrary
external commands. `shell=False` avoids shell parsing, but it does not sandbox the
command. Documentation content must not choose executables. Process extensions may
receive project documentation content and selected metadata. By default, process
extensions inherit the parent process environment; configured environment overlays add
to that environment rather than replacing it. Configure commands deliberately, avoid
logging secrets, and pass provider credentials only to trusted adapters. The process
runtime is a protocol boundary, not a sandbox.

## Failure Behavior

Normal mode reports concise diagnostics:

```text
Failed to load extension:
.ai-doc/extensions/custom_rules.py

Reason:
Analyzer registration must provide an object with analyze(context).
```

Debug mode includes stack details where supported.

Process runtime failures use the same concise style:

```text
Process extension returned an error: {"code": "counter_unavailable", "message": "counter offline"}
```
