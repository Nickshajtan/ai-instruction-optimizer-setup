# Hierarchical Config Example

Use this example to understand nested `.ai-doc.yaml` behavior.

## What It Demonstrates

- Root configuration discovers root docs and package docs.
- Nested configuration is scoped relative to the nested directory.
- `include`, `exclude`, `profiles`, `loading`, and `extensions` accumulate with scoped
  paths.
- `budgets`, `pricing`, and `evaluation` merge like dictionaries.
- `optimization` is replaced by the nested config when a nested config sets it.

## Run

```bash
ai-doc check examples/hierarchical-config
```

## Expected Result

The backend package `AGENTS.md` and public docs are included, while
`packages/backend/docs/private.md` is excluded by the nested config.

## Evidence Tier

A0 deterministic static analysis.

## Network Or Model Access

None.
