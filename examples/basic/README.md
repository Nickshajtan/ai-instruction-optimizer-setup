# Basic Example

Use this example for the smallest useful `ai-doc` workflow.

## What It Demonstrates

- A0 deterministic static analysis of `AGENTS.md` and referenced docs.
- A project-local analyzer extension.
- A first-run command that needs no model credentials.

## Run

```bash
ai-doc check examples/basic
```

## Expected Result

The command analyzes the example repository and reports deterministic findings such as
duplicate guidance and clarity issues. It does not call external models.

## Evidence Tier

A0 deterministic static analysis.

## Network Or Model Access

None.
