# Extensions Example

Use this example to see the provider-neutral process evaluator ABI.

## What It Demonstrates

- `extension_runtime.evaluators` maps a logical evaluator name to an executable.
- `ProcessEvaluator` uses `ProcessTransport` and the `ai-doc.extension/v1` protocol.
- The external executable writes machine JSON to stdout and diagnostics to stderr.

## Run

```bash
ai-doc check examples/extensions --deep
```

## Expected Result

The configured evaluator runs `examples/extensions/simple_evaluator.py` and returns a
passing evaluation for the configured scenario.

## Evidence Tier

B-style configured evaluator evidence for the deep check path. The example uses a
deterministic local executable, not a paid model.

## Network Or Model Access

None.
