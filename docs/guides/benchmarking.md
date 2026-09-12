# Empirical Benchmarking

`ai-doc` should not claim that an instruction rewrite is better only because a heuristic or LLM evaluator assigns it a higher score. The evidence layer measures whether the rewritten repository instructions improve real agent-task outcomes.

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

The benchmark engine therefore acts as an empirical regression layer for the optimizer rather than as another Markdown score.

## Engine versus corpus

Keep two concepts separate:

1. **Benchmark engine** — part of the shipped `ai-doc` package and standalone executable. It reads compatible evidence JSON and produces summaries/decisions.
2. **Benchmark corpus/evidence** — development and research data produced by real repeated agent runs. The project's empirical corpus belongs under `benchmarks/` in this repository and is not required in repositories that only consume `ai-doc`.

`examples/benchmark/example-evidence.json` is synthetic fixture data. It exists to validate the schema, CLI, examples, and CI wiring. It must not be cited as evidence that the optimizer improves a real agent.

## Evidence model

Each benchmark case identifies a repository snapshot and one representative engineering task. Run the same task against the two instruction variants and record multiple runs because coding-agent behavior is stochastic.

Each run can capture task success, instruction violations, retries, input/output tokens, latency, cost, an optional task score, and agent/provider/model metadata including a seed where the provider exposes one.

Use `pair_id` when a baseline run and candidate run were executed as the same experimental pair, for example under the same seed or controlled environment. Explicit pair IDs are preferred because evidence files may be reordered safely. Evidence without `pair_id` remains backward compatible and falls back to positional pairing.

Use deterministic tests or task-specific assertions as the primary success oracle whenever possible. Semantic judging is a secondary signal, not a replacement for executable verification.

## Run a benchmark summary

```bash
ai-doc benchmark examples/benchmark/example-evidence.json
```

The command reports each metric separately instead of collapsing clarity, task quality, and cost into one magic score. Summaries include mean, median, standard deviation, and paired deltas. Task-success decisions are variance-aware:

- fewer than `--minimum-runs` paired runs => `inconclusive`;
- the 95% interval must clear `--minimum-meaningful-improvement` to call an improvement or regression;
- otherwise the result remains `inconclusive`.

Example stricter gate:

```bash
ai-doc benchmark evidence.json --minimum-runs 5 --minimum-meaningful-improvement 0.10
```

For CI:

```bash
ai-doc benchmark evidence.json --fail-on-regression
```

Exit code `5` is used only when at least one case has a meaningful task-success regression. An inconclusive result remains non-blocking. This deliberately makes "leave the instructions unchanged" a normal outcome instead of forcing every optimization attempt to produce a winner.

## Recommended benchmark design

Start with one agent and one model before adding provider breadth. A useful portfolio/release benchmark should eventually cover 10-20 repositories and 5-10 representative tasks per repository. Preserve the repository commit, task definition, verification rubric, raw run artifacts, model/provider/version, pair/seed information where available, and relevant runtime configuration.

Report at least:

- task success rate;
- instruction violations;
- retries;
- input and output tokens;
- estimated cost;
- latency;
- variance, median, confidence interval, and run count.

Do not hide regressions behind aggregate averages. Keep per-case evidence so users can see when shorter instructions save tokens but reduce task reliability. Token reduction and semantic/task quality are independent dimensions; a cheaper candidate is not automatically a better candidate.

## Corpus and regression CI

`examples/benchmark/` is synthetic and exists only to exercise the stable evidence contract. Real publishable evidence belongs under `benchmarks/evidence/`; see `benchmarks/README.md` for the corpus contract. The `Benchmark evidence` workflow evaluates committed evidence and blocks meaningful task regressions while allowing statistically inconclusive results.

Use `docs/case-studies/TEMPLATE.md` when turning a benchmark slice into a published case study. Never fill the results section with invented example percentages and present them as empirical evidence.

## Agent adapters

The evidence JSON is intentionally agent-neutral. Codex, Claude, Copilot, Promptfoo, DeepEval, or a custom harness can produce the raw runs. This keeps the benchmark contract stable while agent SDKs and CLIs change quickly.

If one instruction set behaves differently across agents, preserve that difference in the run metadata rather than averaging it away. That evidence can justify a common instruction core plus thin agent-specific overlays.

## Runtime requirements

Core benchmarking has no Node.js dependency:

- core analysis, optimization, CLI, and benchmark aggregation: Python;
- DeepEval integration: optional Python dependency;
- Promptfoo integration: optional integration that may require Node.js/npm/npx;
- real coding-agent execution: external adapter/harness, not part of the core benchmark aggregator.

A user running the normal standalone `ai-doc` executable does not need Node.js merely because the project supports Promptfoo. Node/npm/npx become relevant only when that optional integration is selected.

`ai-doc doctor` reports the Python/runtime mode, Node/npx availability, optional evaluator dependencies, provider credentials, and `AI_DOC_SEMANTIC_COMMAND` configuration so missing optional runtime pieces are visible before a benchmark or optimization run.
