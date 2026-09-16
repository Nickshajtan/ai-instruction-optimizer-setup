# AI Documentation Optimizer

`ai-doc` analyzes and improves the repository interface consumed by coding agents:
`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, GitHub Copilot instructions, Cursor rules,
agent skills, and related documentation.

It is not just a Markdown linter. It helps answer:

- Are agent instructions clear, consistent, and reachable?
- How are instruction files classified and expected to enter context, based on supported
  conventions and project configuration?
- Did a proposed documentation change preserve critical behavior?
- When a target adapter is configured, what does that target plan to do, and what does it
  report or change during execution?

The first useful workflow is local and deterministic:

```bash
python -m pip install -e ".[dev]"
ai-doc init .
ai-doc check .
```

## Evidence Pyramid

```text
                         C2
                    real execution
                         |
                         C1
                    real planning
                         |
                          B
                 predictive judge
                         |
                         A1
                local semantic ML
                         |
                         A0
              deterministic static

higher: stronger behavioral evidence and greater runtime/cost
lower:  cheaper, faster, and suitable for every PR
```

Higher tiers are not universally "more correct"; they answer different questions and use
different evidence.

- A0/A1 analyze the repository's modeled instruction interface using discovered files,
  configuration, supported conventions, and local analysis.
- B predicts whether a baseline or candidate instruction set is semantically better.
- C1 observes what the configured target adapter plans for concrete scenarios.
- C2 observes what the configured target adapter reports doing and what changed in an
  isolated workspace copy.
- C3 repeated execution/statistical benchmarking is intentionally not part of the current
  architecture.

## Command Map

| Command | Purpose | Evidence | External model required |
|---|---|---|---|
| `ai-doc check .` | Analyze discovered repository instructions and docs | A0, optional A1 | No |
| `ai-doc optimize .` | Generate and evaluate candidate documentation improvements | A0/A1 plus optional B | Depends on configured semantic provider/evaluator |
| `ai-doc probe .` | Ask the configured target adapter for planning observations | C1 | Yes, except fake/demo adapters |
| `ai-doc execute .` | Run the configured target adapter in an isolated workspace copy | C2 | Yes, except fake/demo adapters |
| `ai-doc doctor .` | Inspect runtime/configuration capabilities | diagnostics | No |
| `ai-doc init .` | Create starter `.ai-doc.yaml` and eval scaffold | setup | No |

## Quick Start

Run the deterministic example:

```bash
ai-doc check examples/basic
```

Try the process-extension runtime without paid services:

```bash
ai-doc check examples/extensions --deep --non-interactive
```

Try C1/C2 with the fake target adapter:

```bash
export AI_DOC_TARGET_COMMAND="python fake_target.py"
ai-doc probe examples/target-probe
ai-doc execute examples/target-probe
```

On Windows PowerShell:

```powershell
$env:AI_DOC_TARGET_COMMAND = "$((Get-Command python).Source) fake_target.py"
ai-doc probe examples/target-probe
ai-doc execute examples/target-probe
```

The fake target is executed with `examples/target-probe` as its working directory, so the
command names `fake_target.py` directly.

## Discovery, Profiles, And Loading Evidence

These are built-in discovery and profile defaults. Project configuration can add or
remove patterns. Discovery means `ai-doc` found and parsed a file; it does not by itself
prove when Claude, Codex, Copilot, Cursor, Gemini, or another runtime loads that file.

```text
file discovered
        |
profile / metadata interpreted
        |
configured or approximated context behavior
        !=
observed target-agent loading behavior
```

| Ecosystem | Built-in discovery | Default profile interpretation | Runtime loading semantics |
|---|---|---|---|
| Generic/interoperable | `AGENTS.md`, `.agents/skills/**/SKILL.md` | root instructions and skill docs | Project configuration and deterministic approximation only |
| Codex | `AGENTS.md`, `.codex/skills/**/SKILL.md` | root instructions and skill docs | Runtime-specific loader is deferred |
| Claude | `CLAUDE.md`, `.claude/skills/**/SKILL.md` | root instructions and skill docs | Runtime-specific loader is deferred |
| Gemini | `GEMINI.md`, `.gemini/skills/**/SKILL.md`, `.agents/skills/**/SKILL.md` | root instructions and skill docs | No native SDK/runtime loader in core |
| GitHub Copilot | `.github/copilot-instructions.md`, `AGENTS.md`, `.github/instructions/**/*.instructions.md` | instructions | Runtime-specific loader is deferred |
| Cursor | `AGENTS.md`, `.cursor/rules/**/*.mdc` | instructions | No native SDK/runtime loader in core |

Copilot `.instructions.md` files and Cursor `.mdc` rules are parsed as Markdown-like
documents with their frontmatter preserved in the document text. Frontmatter or known
file formats may provide scoping metadata, but format recognition is weaker evidence than
observing a real target runtime. `ai-doc` does not add Gemini, Copilot, Cursor, Claude,
or Codex SDK integrations to core merely because it discovers their instruction files.

Effective-context selection used by semantic evaluation and probes is deterministic and
auditable, but it is still an approximation. `loading` configuration declares the model
used for analysis and cost estimation; it does not discover how often a real agent loads a
document unless a C-tier adapter supplies that observation.

## Configuration Hierarchy

```text
built-in defaults
        |
root .ai-doc.yaml
        |
nested .ai-doc.yaml
        |
CLI/runtime overrides where applicable
```

Nested configuration is scoped, not a generic deep override.

- `include`, `exclude`, `profiles`, `loading`, and `extensions` accumulate with paths
  scoped relative to the nested config directory.
- `budgets`, `pricing`, and `evaluation` merge like dictionaries.
- `extension_runtime.evaluators` merges by logical evaluator name.
- `optimization` is replaced when a nested config explicitly sets it.
- An explicit `--config` file does not implicitly merge nested `.ai-doc.yaml` files.

Generated starter config stays concise. It includes user-facing discovery/profile
defaults but does not serialize empty/default-only sections merely to mirror every
Pydantic field.

## External Capability Runtime

Process-backed capabilities use a provider-neutral runtime:

```text
logical capability
        |
configured or registered implementation
        |
process adapter where applicable
        |
ProcessTransport
        |
external executable
```

For the current process evaluator path, configuration names a logical evaluator and maps
it to a command under `extension_runtime.evaluators`. The command speaks the
`ai-doc.extension/v1` stdin/stdout protocol. Details live in
[Extension Runtime Configuration](docs/guides/extension-runtime-configuration.md) and
[Extension API](docs/guides/extensions.md). Other registry surfaces exported through
`ai_doc.api.v1` are programmatic composition boundaries unless their configuration path
is explicitly documented.

## Examples

The examples are executable and covered by deterministic CI:

- [basic](examples/basic/README.md): minimum A0 static workflow.
- [extensions](examples/extensions/README.md): process-backed evaluator runtime.
- [conflicting-instructions](examples/conflicting-instructions/README.md): known
  deterministic findings.
- [hierarchical-config](examples/hierarchical-config/README.md): nested config merge and
  scoping semantics.
- [semantic](examples/semantic/README.md): optional A1 local semantic analysis.
- [multi-agent](examples/multi-agent/README.md): coexistence of major agent ecosystems.
- [target-probe](examples/target-probe/README.md): deterministic C1/C2 fake target.

## Optional Local Semantic ML

A1 local semantic analysis uses locally provisioned sentence-transformer/NLI models:

```bash
python -m pip install -e ".[ml]"
```

Normal `ai-doc check` runs do not silently download models. Configure `local_ml`
explicitly and provide local model artifacts through explicit paths, `AI_DOC_MODEL_ROOT`,
a local cache, or a packaged model bundle. See
[Analysis Pyramid](docs/design/analysis-pyramid.md) and
[Packaging](docs/operations/packaging.md).

## Optional Predictive Evaluation

`ai-doc optimize` and `ai-doc check --deep` can use optional evaluator/provider
integrations for B-tier predictive evidence. Promptfoo and DeepEval remain optional, and
provider-backed semantic optimization uses the provider-neutral `AI_DOC_SEMANTIC_COMMAND`
contract. See [Semantic Optimization](docs/guides/semantic-optimization.md) and
[Predictive Semantic Evaluation](docs/design/predictive-evaluation.md).

## C1 Planning And C2 Execution

C1 planning:

```bash
export AI_DOC_TARGET_COMMAND='your-target-adapter'
ai-doc probe .
```

C2 execution:

```bash
export AI_DOC_TARGET_COMMAND='your-target-adapter'
ai-doc execute .
```

The target command is trusted project/runtime configuration and runs with `shell=False`.
C2 uses a temporary workspace copy and independently records filesystem deltas. This is
workspace isolation, not an OS sandbox. See
[Behavioral Evaluation](docs/design/behavioral-evaluation.md) and
[Execution Probes](docs/design/execution-probes.md).

## Distribution

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

## What Is Stable

The public contract is limited to:

- CLI commands, options, and exit codes;
- JSON output schemas;
- `.ai-doc.yaml` configuration;
- documented project-local extensions, including configured static analyzers and
  process-backed evaluators;
- explicit exports from `ai_doc.api.v1`.

Internal optimizer, parser, storage, Promptfoo, DeepEval, provider, local-ML adapter,
target-command adapter, and GEPA modules are not extension contracts.

## Documentation

Use these when you want to run or configure the tool:

- [Getting Started](docs/guides/getting-started.md): install modes, first run, and common commands.
- [Runbook](docs/operations/runbook.md): routine operation, CI usage, diagnosis, and recovery.
- [Configuration](docs/guides/configuration.md): `.ai-doc.yaml`, profiles, budgets, evals, optimization, and extensions.
- [Semantic Optimization](docs/guides/semantic-optimization.md): semantic generation/evaluation, invariant safety, budgets, Pareto comparison, repair, and evidence.

Use these when changing the project:

- [Standards](docs/standards.md): normative coding, API, CLI, configuration, security, testing, and documentation rules.
- [Architecture](docs/design/architecture.md): package boundaries, flows, stable contracts, and adapter responsibilities.
- [Analysis Pyramid](docs/design/analysis-pyramid.md): A0 deterministic analysis, optional A1 local ML, extension points, limits, and the boundary to B/C evidence.
- [Predictive Semantic Evaluation](docs/design/predictive-evaluation.md): B-tier pairwise judgment, uncertainty, recommendation interaction, and the boundary to empirical C-tier evidence.
- [Behavioral Evaluation](docs/design/behavioral-evaluation.md): C1 real-target planning probes and the target command contract.
- [Execution Probes](docs/design/execution-probes.md): C2 execution probes, workspace isolation, and filesystem deltas.
- [Design Decisions](docs/design/decisions.md): rationale and trade-offs behind major choices.
- [Testing And Release](docs/operations/testing-and-release.md): verification commands, smoke tests, CI, and release checklist.

Use these for integration or distribution:

- [Extension API](docs/guides/extensions.md): stable `ai_doc.api.v1` imports, custom analyzer extensions, and process evaluator extensions.
- [Packaging](docs/operations/packaging.md): source checkout, wheel, executable builds, checksums, local model bundles, and limitations.
- [Deferred Work](docs/design/deferred.md): intentionally postponed capabilities and known limitations.

## Exit Codes

- `0`: success or no blocking findings.
- `1`: internal, tool, or configuration error.
- `2`: static quality gate failed.
- `3`: semantic evaluation gate failed.
- `4`: optimization produced no acceptable candidate.
