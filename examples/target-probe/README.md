# Target Probe Example

Use this example to run C1 planning and C2 execution probes without paid models.

## What It Demonstrates

- `AI_DOC_TARGET_COMMAND` as the provider-neutral target command boundary.
- C1 planning observations through `ai-doc probe`.
- C2 execution observations through `ai-doc execute`.
- Workspace mutation happens in an isolated temporary copy.

## Run

PowerShell:

```powershell
$env:AI_DOC_TARGET_COMMAND = "$((Get-Command python).Source) fake_target.py"
ai-doc probe examples/target-probe
ai-doc execute examples/target-probe
```

Bash:

```bash
export AI_DOC_TARGET_COMMAND="python fake_target.py"
ai-doc probe examples/target-probe
ai-doc execute examples/target-probe
```

## Expected Result

`probe` reports planned actions from the fake target. `execute` reports a created
`target-output.txt` file in the isolated execution workspace, while the source example
directory remains unchanged.

## Evidence Tier

C1 planning and C2 execution, using a deterministic fake target.

## Network Or Model Access

None.
