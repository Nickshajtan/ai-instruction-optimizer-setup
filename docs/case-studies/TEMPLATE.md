# Case study: <repository / scenario>

> Status: empirical evidence required. Do not publish placeholder numbers as results.

## Question

What repository-to-agent behavior are we trying to improve, and why does it matter?

## Repository snapshot

- Repository/revision:
- Repository shape:
- Instruction files in scope:
- Baseline instruction tokens:
- Candidate instruction tokens:

## Task set

Describe the representative engineering tasks and their deterministic verification or rubric. Explain why the tasks exercise the instructions being optimized.

## Runtime

- Agent:
- Provider:
- Model/version:
- Runs per variant:
- Seed/config where available:
- Relevant environment/tool permissions:

## Results

Report baseline and candidate separately for task success, instruction violations, retries, input/output tokens, latency, and cost. Include median, variance, confidence interval, and raw run count. Keep per-task results visible instead of hiding regressions behind an aggregate average.

## Interpretation

Explain which deltas are meaningful, which remain inconclusive, and whether the candidate should replace the baseline. A no-op is an acceptable conclusion.

## Risks and regressions

Document any task class, agent, or repository shape where the optimized instructions performed worse or where evidence is too noisy.

## Reproduction

Point to the benchmark evidence file, repository revision, task definitions, and commands required to reproduce the report.
