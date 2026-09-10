# Empirical Benchmarking

`ai-doc` should not claim that an instruction rewrite is better only because a heuristic or LLM evaluator assigns it a higher score. The evidence layer measures whether the rewritten repository instructions improve real agent-task outcomes.

## Evidence model

Each benchmark case identifies a repository snapshot and one representative engineering task. Run the same task against two instruction variants:

- `baseline`: the original repository instructions;
- `candidate`: the optimized instructions.

Record multiple runs for each variant because coding-agent behavior is stochastic. Each run can capture task success, instruction violations, retries, input/output tokens, latency, cost, an optional task score, and agent/provider/model metadata.

Use deterministic tests or task-specific assertions as the primary success oracle whenever possible. Semantic judging is a secondary signal, not a replacement for executable verification.

## Run a benchmark summary

```bash
ai-doc benchmark examples/benchmark/evidence.json
```

The command reports each metric separately instead of collapsing clarity, task quality, and cost into one magic score. Task-success decisions are variance-aware:

- fewer than `--minimum-runs` paired runs => `inconclusive`;
- the 95% interval must clear `--minimum-meaningful-improvement` to call an improvement or regression;
- otherwise the result remains `inconclusive`.

Example stricter gate:

```bash
ai-doc benchmark evidence.json --minimum-runs 5 --minimum-meaningful-improvement 0.10
```

A no-op or inconclusive result is valid. The optimizer should not replace repository instructions when the observed gain cannot be distinguished from noise.

## Recommended benchmark design

Start with one agent and one model before adding provider breadth. A useful portfolio/release benchmark should eventually cover 10-20 repositories and 5-10 representative tasks per repository. Preserve the repository commit, task definition, verification rubric, raw run artifacts, model/provider/version, and relevant runtime configuration.

Report at least:

- task success rate;
- instruction violations;
- retries;
- input and output tokens;
- estimated cost;
- latency;
- variance and run count.

Do not hide regressions behind aggregate averages. Keep per-case evidence so users can see when shorter instructions save tokens but reduce task reliability.

## Agent adapters

The evidence JSON is intentionally agent-neutral. Codex, Claude, Copilot, Promptfoo, DeepEval, or a custom harness can produce the raw runs. This keeps the benchmark contract stable while agent SDKs and CLIs change quickly.

Runtime topology remains explicit:

- core analysis and benchmark aggregation: Python;
- DeepEval integration: optional Python dependency;
- Promptfoo integration: optional wrapper that may require Node.js/npm/npx;
- real coding-agent execution: external adapter/harness, not part of the core benchmark aggregator.
