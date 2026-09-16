# Semantic Example

Use this example to experiment with optional A1 local semantic analysis.

## What It Demonstrates

- Lexically different instructions that mean nearly the same thing.
- A semantic contradiction that deterministic literal checks may not fully capture.
- A safe repository fixture when local ML dependencies are not installed.

## Run

Static-only:

```bash
ai-doc check examples/semantic
```

With local semantic ML after installing and provisioning models:

```bash
python -m pip install -e ".[ml]"
ai-doc check examples/semantic
```

## Expected Result

Without local ML, the example remains a normal A0 check. With `local_ml.enabled: true`
and local models available, A1 semantic duplication/contradiction checks can add semantic
evidence.

## Evidence Tier

A0 by default, optional A1 with local ML.

## Network Or Model Access

No network access is required by ordinary CI. Local ML requires locally available model
artifacts.
