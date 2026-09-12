# AI Documentation Optimizer

Repository instructions are part of the interface between repository knowledge and an AI coding agent. `ai-doc` analyzes and optimizes that interface for clarity, consistency, task reliability, and context cost.

The tool combines static analysis, optional semantic evaluation, conservative optimization, and an empirical evidence layer for comparing baseline instructions with optimized instructions on real coding-agent tasks. The intended outcome is not a prettier Markdown file: it is fewer instruction violations and retries, lower context/token cost, and equal or better task success.

`ai-doc` is **not** a generic Grammarly-style Markdown linter, a generic prompt improver, or an LLM wrapper. A no-op is a valid optimization result when evidence does not justify replacing the baseline.

## Install And Run

Editable install for local development:

```bash
python -m pip install -e ".[dev]"
ai-doc check examples/basic
ai-doc optimize examples/basic --strategy balanced --show-frontier
ai-doc benchmark examples/benchmark/example-evidence.json
ai-doc doctor examples/basic
```

Source-checkout mode for use from a target repository's `.tools/ai-doc` directory:

```bash
python tools/bootstrap.py
./ai-doc check ../..
```

Windows PowerShell:

```powershell
python tools/bootstrap.py
.\ai-doc.ps1 check ..\..
```

Standalone executable build:

```bash
python -m tools.build executable
```

The standalone executable is the preferred adoption path for repositories that do not otherwise use Python: consumers do not need to add Python to their application stack. Version tags matching `v*` build release executables for Linux, macOS, and Windows plus the Python distribution and attach them to a GitHub Release.

Optional deep-evaluation setup:

```bash
python -m pip install -e ".[deep]"
ai-doc setup --deep
ai-doc check examples/basic --deep
```

Adaptive optimization can also use the provider-neutral `AI_DOC_SEMANTIC_COMMAND` contract for semantic generation, invariant safety, evaluation, and eligible prompt suboptimization. See [Semantic Optimization](docs/guides/semantic-optimization.md) for the command contract, budget semantics, and evidence model.

## What Benchmarking Means Here

The benchmark is not a performance benchmark for the Python CLI. It is a local empirical comparison of how AI coding agents behave with two versions of repository instructions.

For the same repository task, run the agent repeatedly with:

- `baseline`: the original instructions;
- `candidate`: the optimized instructions.

Then compare outcomes such as task success, instruction violations, retries, input/output tokens, latency, and cost. This answers the local product question: **did this rewritten instruction set actually help the agent for this repository/task, or did it only look cleaner to us?**

The boundary is intentional:

- the benchmark engine is part of `ai-doc` and can evaluate any compatible evidence JSON;
- real benchmark evidence belongs to the local/private environment where the target repository and agent runs exist;
- `ai-doc` does not expect consumer benchmark results, repository snapshots, tasks, or raw agent outputs to be committed back to this repository;
- local evidence may be stored in a temporary directory, ignored workspace directory, or private CI artifact store depending on the user's workflow.

`examples/benchmark/example-evidence.json` is intentionally **synthetic example data** used only to exercise the schema, CLI, tests, and CI contract of the benchmark engine. It is not empirical proof that the optimizer improves Codex, Claude, Copilot, or any other agent.

## Evaluate A Local Optimization Experiment

Static clarity and token metrics are useful signals, but they do not prove that an AI agent performs better. `ai-doc benchmark` consumes a local evidence file containing repeated baseline/candidate task runs and reports task success, instruction violations, retries, tokens, latency, cost, median, variance, and a confidence-aware decision without collapsing them into one magic quality score.

```bash
ai-doc benchmark ./local-evidence.json \
  --minimum-runs 3 \
  --minimum-meaningful-improvement 0.05
```

Use `--fail-on-regression` in a local or private CI workflow when a meaningful task-success regression should fail that experiment. Inconclusive evidence remains non-blocking.

The evidence format is provider-neutral: Codex, Claude, Copilot, Promptfoo, DeepEval, or a custom harness can produce raw runs. See [Empirical Benchmarking](docs/guides/benchmarking.md) for the local evidence model and experimental guidance.

## Runtime Requirements

**Node.js is not a core dependency.** The analyzer, optimizer, benchmark engine, CLI, and standalone executable are Python-based and do not require Node.js/npm/npx for normal operation.

Node.js/npm/npx may be required only when you enable an optional integration that uses them, currently Promptfoo. DeepEval is an optional Python dependency. Real coding-agent execution is also external to the benchmark aggregator and depends on whichever agent CLI, SDK, or harness you choose.

Use `ai-doc doctor` to see which optional runtimes and integrations are available in the current environment. Missing Node/npx is informational unless you are trying to use a Node-based integration.

## Product Direction

- **v0.2 — Prove it works locally:** benchmark contract, repeated evaluation, task-success/cost evidence, and regression decisions for explicit experiments.
- **v0.3 — Make it reliable:** confidence/noise handling, conservative/no-op recommendation gates, invariant protection, and explicit independent metrics.
- **v0.4 — Make it easy to adopt:** release binaries, source-checkout mode, richer `doctor`, stable versioned extension API, and a local-first benchmark harness.

Infrastructure additions should serve measurable benchmark outcomes. New optimizer abstractions or evaluators should come with a concrete scenario demonstrating the additional signal they provide.

## Runtime Topology

- Core analyzer, optimizer, benchmark aggregation: Python only.
- DeepEval adapter: optional Python dependency.
- Promptfoo adapter: optional integration that may require Node.js/npm/npx.
- Real coding-agent execution: external provider/agent adapter or harness; benchmark evidence remains local to that execution environment.

Use `ai-doc doctor` to inspect Python/runtime mode, Node/npx availability, optional integrations, provider credentials, and the provider-neutral semantic command.

## What Is Stable

The public contract is limited to:

- CLI commands, options, and exit codes;
- JSON output schemas, including benchmark evidence/report schemas;
- `.ai-doc.yaml` configuration;
- configured project-local extensions;
- explicit exports from `ai_doc.api.v1`, including `API_VERSION`.

Internal optimizer, parser, storage, Promptfoo, DeepEval, provider, and GEPA modules are not extension contracts.

## Documentation

Use these when you want to run or configure the tool:

- [Getting Started](docs/guides/getting-started.md): install modes, first run, and common commands.
- [Runbook](docs/operations/runbook.md): routine operation, CI usage, diagnosis, and recovery.
- [Configuration](docs/guides/configuration.md): `.ai-doc.yaml`, profiles, budgets, evals, optimization, and extensions.
- [Semantic Optimization](docs/guides/semantic-optimization.md): semantic generation/evaluation, invariant safety, task-selected context, budgets, Pareto comparison, repair, and evidence.
- [Empirical Benchmarking](docs/guides/benchmarking.md): local agent-task evidence, repeated runs, noise handling, and FinOps metrics.

Use these when changing the project:

- [Standards](docs/standards.md): normative coding, API, CLI, configuration, security, testing, and documentation rules.
- [Architecture](docs/design/architecture.md): package boundaries, flows, stable contracts, and adapter responsibilities.
- [Design Decisions](docs/design/decisions.md): rationale and trade-offs behind major choices.
- [Testing And Release](docs/operations/testing-and-release.md): verification commands, smoke tests, CI, and release checklist.

Use these for integration or distribution:

- [Extension API](docs/guides/extensions.md): stable `ai_doc.api.v1` imports, compatibility, deprecation policy, and custom analyzer extensions.
- [Packaging](docs/operations/packaging.md): source checkout, wheel, executable builds, checksums, and limitations.
- [Deferred Work](docs/design/deferred.md): intentionally postponed capabilities and known limitations.

Documentation maintenance rules:

- Keep usage instructions in [Getting Started](docs/guides/getting-started.md) or [Runbook](docs/operations/runbook.md).
- Keep architecture rationale in [Architecture](docs/design/architecture.md) or [Design Decisions](docs/design/decisions.md).
- Keep normative project rules in [Standards](docs/standards.md).
- Keep general documentation-writing guidance in [docs/AGENTS.md](docs/AGENTS.md).
- Keep agent-only workflow instructions in `.ai/skills/`.
- Keep Codex and Claude routing in `.codex/skills/` and `.claude/skills/` adapter skills.
- Keep root-level `README.md`, `ARCHITECTURE.md`, and `DEFERRED.md` as entry points, not competing sources of truth.

## Exit Codes

- `0`: success or no blocking findings.
- `1`: internal, tool, or configuration error.
- `2`: static quality gate failed.
- `3`: semantic evaluation gate failed.
- `4`: optimization produced no acceptable candidate.
- `5`: local benchmark regression gate detected a meaningful task-success regression.
