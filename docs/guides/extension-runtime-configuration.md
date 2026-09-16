# Extension Runtime Configuration

Use `extension_runtime` when a project wants to bind a logical evaluator name to an executable process.

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

`evaluation.deep.evaluator` selects a logical name. `extension_runtime.evaluators`
defines how that name is implemented. This lets the same `ai-doc` configuration shape
work with an executable wrapper around Claude, Codex, Gemini, local models, rules
engines, or any other trusted process that speaks the protocol. The adapter command owns
any provider authentication, SDK usage, and runtime-specific prompt formatting; merely
configuring a command does not make the evidence equivalent to a native runtime loader or
agent integration.

Commands are argv arrays and run without `shell=True`. Configure only trusted executables from trusted project configuration. Documentation content should not choose or rewrite the command.

The command receives protocol JSON on stdin, writes protocol JSON on stdout, and writes diagnostics on stderr. `ProcessTransport` owns those process and protocol mechanics; `ProcessEvaluator` only maps evaluator inputs and outputs around the transport. See [Extension API](extensions.md) for the request and response schema.
