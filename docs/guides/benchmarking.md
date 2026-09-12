# Empirical Benchmarking

`ai-doc` should not claim that an instruction rewrite is better only because a heuristic or LLM evaluator assigns it a higher score. The evidence layer measures whether rewritten repository instructions improve real agent-task outcomes in an explicit local experiment.

## What the benchmark is

This is **not** a CPU/runtime benchmark for the `ai-doc` Python code. It is a controlled before/after experiment for repository instructions.

For one repository task, compare two instruction variants:

- `baseline`: the original repository instructions;
- `candidate`: the optimized instructions.

Run the same engineering task multiple times against both variants and record what actually happened. The benchmark then answers questions such as:

- Did task success improve or regress?
- Did the agent violate fewer instructions?
- Did it need fewer retries?
- Did the instruction change reduce input/output tokens or cost?
- Did latency improve without sacrificing reliability?

The benchmark engine therefore acts as an empirical regression layer for a specific experiment rather than as another Markdown score.

## Local-only evidence boundary

Keep two concepts separate:

1. **Benchmark engine** — part of the shipped `ai-doc` package and standalone executable. It reads compatible evidence JSON and produces summaries/decisions.
2. **Real benchmark evidence** — local/private experiment data produced from a target repository and real agent runs.

Real evidence is intentionally **not** a repository contribution mechanism. `ai-doc` does not expect consumer repository snapshots, task definitions, raw prompts, raw agent outputs, costs, credentials, or evidence JSON to be committed back to the AI Documentation Optimizer repository.

Store real evidence where the experiment belongs, for example:

- a temporary local directory;
- an ignored directory inside the consumer workspace;
- a private CI artifact store;
- another private research location chosen by the consumer.

The source repository contains only `examples/benchmark/example-evidence.json`, a synthetic fixture used to validate the schema, CLI, tests, and benchmark contract. It must not be cited as evidence that the optimizer improves a real agent.

## Evidence model

Each benchmark case identifies a repository snapshot and one representative engineering task. Run the same task against the two instruction variants and record multiple runs because coding-agent behavior is stochastic.

Each run can capture task success, instruction violations, retries, input/output tokens, latency, cost, an optional task score, and agent/provider/model metadata including a seed where the provider exposes one.

Use `pair_id` when a baseline run and candidate run were executed as the same experimental pair, for example under the same seed or controlled environment. Explicit pair IDs are preferred because evidence files may be reordered safely. Evidence without `pair_id` remains backward compatible and falls back to positional pairing.

Use deterministic tests or task-specific assertions as the primary success oracle whenever possible. Semantic judging is a secondary signal, not a replacement for executable verification.

## Run a benchmark summary

Run the command against a local evidence file:

```bash
ai-doc benchmark ./local-evidence.json
```

The command reports each metric separately instead of collapsing task quality and cost into one magic score. Summaries include mean, median, standard deviation, and paired deltas. Task-success decisions are variance-aware:

- fewer than `--minimum-runs` paired runs => `inconclusive`;
- the 95% interval must clear `--minimum-meaningful-improvement` to call an improvement or regression;
- otherwise the result remains `inconclusive`.

Example stricter gate:

```bash
ai-doc benchmark ./local-evidence.json --minimum-runs 5 --minimum-meaningful-improvement 0.10
```

For a local or private CI experiment:

```bash
ai-doc benchmark ./local-evidence.json --fail-on-regression
```

Exit code `5` is used only when at least one case has a meaningful task-success regression. An inconclusive result remains non-blocking. This deliberately makes "leave the instructions unchanged" a normal outcome instead of forcing every optimization attempt to produce a winner.

The repository's own `Benchmark contract` workflow does **not** evaluate consumer evidence. It only runs the synthetic fixture to ensure that the benchmark schema, CLI, and evaluator continue to work.

## Recommended experiment design

Start with one agent and one model before adding provider breadth. Preserve enough local metadata to reproduce the experiment: repository revision, task definition, verification rubric, raw run artifacts, model/provider/version, pair/seed information where available, and relevant runtime configuration.

Report at least:

- task success rate;
- instruction violations;
- retries;
- input and output tokens;
- estimated cost;
- latency;
- variance, median, confidence interval, and run count.

Do not hide regressions behind aggregate averages. Keep per-case evidence in the local experiment so it is visible when shorter instructions save tokens but reduce task reliability. Token reduction and semantic/task quality are independent dimensions; a cheaper candidate is not automatically a better candidate.

A single experiment is local evidence for that repository/task/runtime combination. Broader product claims require separate research across multiple repositories and tasks, but that research dataset is not part of the consumer-data contract and does not belong in the product repository by default.

## Agent adapters

The evidence JSON is intentionally agent-neutral. Codex, Claude, Copilot, Promptfoo, DeepEval, or a custom harness can produce the raw runs. This keeps the benchmark contract stable while agent SDKs and CLIs change quickly.

If one instruction set behaves differently across agents, preserve that difference in the local run metadata rather than averaging it away.

## Runtime requirements

Core benchmarking has no Node.js dependency:

- core analysis, optimization, CLI, and benchmark aggregation: Python;
- DeepEval integration: optional Python dependency;
- Promptfoo integration: optional integration that may require Node.js/npm/npx;
- real coding-agent execution: external adapter/harness, not part of the core benchmark aggregator.

A user running the normal standalone `ai-doc` executable does not need Node.js merely because the project supports Promptfoo. Node/npm/npx become relevant only when that optional integration is selected.

`ai-doc doctor` reports the Python/runtime mode, Node/npx availability, optional evaluator dependencies, provider credentials, and `AI_DOC_SEMANTIC_COMMAND` configuration so missing optional runtime pieces are visible before a benchmark or optimization run.
