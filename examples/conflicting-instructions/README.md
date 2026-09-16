# Conflicting Instructions Example

Use this example to see concrete deterministic findings on an intentionally flawed
agent instruction interface.

## What It Demonstrates

- Literal contradiction.
- Repeated instruction text.
- Ambiguous guidance.
- Oversized/redundant context pressure.

## Run

```bash
ai-doc check examples/conflicting-instructions
```

## Expected Result

The command should emit stable finding codes including:

- `RISK_LITERAL_CONTRADICTION`
- `FINOPS_DUPLICATE_LIST_ITEM`
- `CLARITY_AMBIGUOUS_RULE`

## Evidence Tier

A0 deterministic static analysis.

## Network Or Model Access

None.
