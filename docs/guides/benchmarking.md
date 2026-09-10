# Empirical Benchmarking

`ai-doc` should not claim that an instruction rewrite is better only because a heuristic or LLM evaluator assigns it a higher score. The evidence layer measures whether the rewritten repository instructions improve real agent-task outcomes.

## Evidence model

Each benchmark case identifies a repository snapshot and one representative engineering task. Run the same task against two instruction variants:

- `baseline`: the original repository instructions;
- `candidate`: the optimized instructions.

Record multiple runs for each variant because coding-agent behavior is stochastic. Each run can capture task success, instruction violations, retries, input/output tokens, latency, cost, an optional task score, and agent/provider/model metadata including a seed where the provider exposes one.

Use deterministic tests or task-specific assertions as the primary success oracle whenever possible. Semantic judging is a secondary signal, not a replacement for executable verification.

## Run a benchmark summary

```bash
ai-doc benchmark examples/benchmark/evidence.json
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

Start with one agent and one model before adding provider breadth. A useful portfolio/release benchmark should eventually cover 10-20 repositories and 5-10 representative tasks per repository. Preserve the repository commit, task definition, verification rubric, raw run artifacts, model/provider/version, seed where available, and relevant runtime configuration.

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

Runtime topology remains explicit:

- core analysis and benchmark aggregation: Python;
- DeepEval integration: optional Python dependency;
- Promptfoo integration: optional wrapper that may require Node.js/npm/npx;
- real coding-agent execution: external adapter/harness, not part of the core benchmark aggregator.

`ai-doc doctor` reports the Python/runtime mode, Node/npx availability, optional evaluator dependencies, provider credentials, and `AI_DOC_SEMANTIC_COMMAND` configuration so missing runtime pieces are visible before a benchmark or optimization run.
