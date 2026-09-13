# AI Documentation Optimizer

`ai-doc` is a Python CLI for analyzing Markdown documentation used by AI coding agents.
It reports clarity, structure, and context-cost issues, supports optional lexical/semantic
evaluation, and can generate optimization candidates without modifying source files.

## Install And Run

Editable install for local development:

```bash
python -m pip install -e ".[dev]"
ai-doc check examples/basic
ai-doc optimize examples/basic --strategy balanced --show-frontier
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

Optional local semantic static analysis (A1):

```bash
python -m pip install -e ".[ml]"
```

A1 uses locally provisioned sentence-transformer/NLI models and never requires an external inference API. Model artifacts are not downloaded silently by normal `ai-doc check` runs; enable and configure `local_ml` explicitly. Models can come from explicit local paths, `AI_DOC_MODEL_ROOT`, a local cache, or a fully embedded standalone model bundle. See [Analysis Pyramid](docs/design/analysis-pyramid.md) and [Packaging](docs/operations/packaging.md).

Optional deep-evaluation setup:

```bash
python -m pip install -e ".[deep]"
ai-doc setup --deep
ai-doc check examples/basic --deep
```

Adaptive optimization can also use the provider-neutral `AI_DOC_SEMANTIC_COMMAND` contract for semantic generation, invariant safety, evaluation, and eligible prompt suboptimization. See [Semantic Optimization](docs/guides/semantic-optimization.md) for the command contract, budget semantics, and evidence model.

Optional pairwise B-tier judging can compare baseline and candidate documentation for predicted instruction-following quality without claiming empirical target-agent performance. See [Predictive Semantic Evaluation](docs/design/predictive-evaluation.md).

## What Is Stable

The public contract is limited to:

- CLI commands, options, and exit codes;
- JSON output schemas;
- `.ai-doc.yaml` configuration;
- configured project-local extensions;
- explicit exports from `ai_doc.api.v1`.

Internal optimizer, parser, storage, Promptfoo, DeepEval, provider, local-ML adapter, and GEPA modules are not extension contracts.

## Documentation

Use these when you want to run or configure the tool:

- [Getting Started](docs/guides/getting-started.md): install modes, first run, and common commands.
- [Runbook](docs/operations/runbook.md): routine operation, CI usage, diagnosis, and recovery.
- [Configuration](docs/guides/configuration.md): `.ai-doc.yaml`, profiles, budgets, evals, optimization, and extensions.
- [Semantic Optimization](docs/guides/semantic-optimization.md): semantic generation/evaluation, invariant safety, task-selected context, budgets, Pareto comparison, repair, and evidence.

Use these when changing the project:

- [Standards](docs/standards.md): normative coding, API, CLI, configuration, security, testing, and documentation rules.
- [Architecture](docs/design/architecture.md): package boundaries, flows, stable contracts, and adapter responsibilities.
- [Analysis Pyramid](docs/design/analysis-pyramid.md): A0 deterministic analysis, optional A1 local ML, extension points, limits, and the boundary to B/C evidence.
- [Predictive Semantic Evaluation](docs/design/predictive-evaluation.md): B-tier pairwise judgment, DeepEval/provider adapters, uncertainty, recommendation interaction, and the boundary to empirical C-tier execution.
- [Design Decisions](docs/design/decisions.md): rationale and trade-offs behind major choices.
- [Testing And Release](docs/operations/testing-and-release.md): verification commands, smoke tests, CI, and release checklist.

Use these for integration or distribution:

- [Extension API](docs/guides/extensions.md): stable `ai_doc.api.v1` imports and custom analyzer extensions.
- [Packaging](docs/operations/packaging.md): source checkout, wheel, executable builds, checksums, local model bundles, and limitations.
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
