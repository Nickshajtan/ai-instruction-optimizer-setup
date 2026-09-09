# Extension API

Project-local extensions let repositories add custom checks without forking `ai-doc`.

Use this page when the built-in analyzers are not enough and your organization needs a
repository-specific rule. If you only want to configure which files are analyzed, use
[Configuration](configuration.md) instead.

An extension is a Python file listed in `.ai-doc.yaml`. `ai-doc` imports that file and
calls its `register(registry)` function. The extension can then add static analyzers that
receive the parsed documentation snapshot and return findings.

## Where Extensions Run

The current extension API is for static analysis only.

Extensions run when a command loads the static analyzer pipeline:

- `ai-doc check`
- `ai-doc check --deep`, before the optional deep evaluator runs
- `ai-doc optimize`, for baseline and candidate static gates

Extensions do not currently extend:

- `ai-doc init`, `doctor`, `setup`, or `version`
- Promptfoo or DeepEval evaluator internals
- candidate generation strategies
- Pareto recommendation policy
- token counters, pricing providers, or document profiles
- packaging/build behavior

This means custom analyzers can add findings to reports, and those findings can influence
static gates during optimization. They are not a general plugin system for every command.

## Stability Contract

Stable imports live under:

```python
from ai_doc.api.v1 import AnalysisContext, Finding
```

Anything outside `ai_doc.api.v1` should be treated as internal unless explicitly
documented otherwise.

## Configure Extensions

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

Because extension code runs with normal Python privileges, only configure files that are
part of the trusted repository.

## Analyzer Extension

This example reports an informational finding whenever a document mentions generated
files. Real extensions can enforce organization-specific policies, naming conventions, or
required runbook links.

```python
from ai_doc.api.v1 import AnalysisContext, Finding


class GeneratedFilesPolicy:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        findings: list[Finding] = []
        for document in context.snapshot.documents:
            if "generated files" in document.text.lower():
                findings.append(
                    Finding(
                        code="ORG_GENERATED_FILES_POLICY",
                        category="risk",
                        severity="info",
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

## Registration

Extensions must define:

```python
def register(registry) -> None:
    ...
```

The registry validates registrations. A custom analyzer must provide:

```python
def analyze(self, context: AnalysisContext) -> list[Finding]:
    ...
```

`AnalysisContext` gives access to configuration, parsed documents, and the document graph.
`Finding` is the stable report object shown in console and JSON output.

## Failure Behavior

Normal mode reports concise diagnostics:

```text
Failed to load extension:
.ai-doc/extensions/custom_rules.py

Reason:
Analyzer registration must provide an object with analyze(context).
```

Debug mode includes stack details where supported.
