# Extension Runtime Configuration

Use `extension_runtime` when a project wants to bind a logical component name to an
executable process.

```yaml
components:
  token_counter: company-counter
  recommendation_policy: company-policy
  provider: company-provider
evaluation:
  deep:
    evaluator: company-evaluator
extension_runtime:
  analyzers:
    company-analyzer:
      type: command
      command: [python, examples/extensions/company.py]
  evaluators:
    company-evaluator:
      type: command
      command: [python, examples/extensions/company.py]
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
      timeout: 120
      env:
        AI_DOC_EXTENSION_MODE: trusted
```

`extension_runtime` makes process implementations available. `components` selects global
token-counter, recommendation-policy, and provider names. `evaluation.deep.evaluator`
selects the evaluator name for deep evaluation. Process analyzers run when configured
because analyzers are additive.

This lets the same `ai-doc` configuration shape work with an executable wrapper around
Claude, Codex, Gemini, local models, rules engines, or any other trusted process that
speaks the protocol. The adapter command owns any provider authentication, SDK usage, and
runtime-specific prompt formatting; merely configuring a command does not make the
evidence equivalent to a native runtime loader or agent integration.

Commands are argv arrays and run without `shell=True`. Configure only trusted
executables from trusted project configuration. Documentation content should not choose
or rewrite the command.

Process extensions do not inherit the full parent environment. `ai-doc` passes only a
small runtime-compatibility environment, such as executable lookup and platform system
root variables when present, and then adds literal values from the component's `env:`
mapping. It does not pass user-home, shell, temporary-directory, or ambient credential
variables by default. Do not place secrets in repository-controlled configuration; use a
trusted wrapper, secret manager, or CI step to provide credentials outside `.ai-doc.yaml`.

The command receives protocol JSON on stdin, writes protocol JSON on stdout, and writes
diagnostics on stderr. `ProcessTransport` owns those process and protocol mechanics;
capability adapters map analyzer, evaluator, token-counter, recommendation, and provider
payloads around the transport. See [Extension API](extensions.md) for the request and
response schema.
