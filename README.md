# AI Documentation Optimizer

`ai-doc` is a quality, evidence, and cost gateway for AI-facing repository documentation.

AI-facing documentation includes `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, agent skills,
GitHub Copilot instructions, Cursor rules, architecture/reference docs, and
project-specific Markdown that agents use as working context. Projects can include
additional Markdown files or globs through `.ai-doc.yaml`.

`ai-doc` does not try to prove that optimized Markdown is universally better for every
LLM or agent. It helps answer bounded repository questions:

- Is AI-facing documentation clear, consistent, and appropriately structured?
- Which documents belong to the modeled AI context, and what roles do they serve?
- Is important knowledge reachable without unnecessarily inflating context?
- Did a proposed documentation change preserve critical behavior?
- When a target adapter is configured, what does that target plan to do, and what does it report or change during execution?

Static findings do not prove that an LLM or agent will fail. Different evidence tiers
answer different questions: deterministic facts and policy violations, local semantic
risk signals, predictive evaluator judgments, or observed target-agent behavior.

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

Higher tiers are not universally "more correct"; they answer different questions and use different evidence.

- A0 deterministic/static verifies structural facts, policy violations, and cheap risk signals.
- A1 local semantic detects probabilistic local semantic signals without external providers.
- B predictive evaluators estimate likely semantic quality or behavior.
- C1 planning probes observe real target planning behavior for configured scenarios.
- C2 execution probes observe real target execution behavior in an isolated workspace copy.
- C3 repeated execution/statistical benchmarking is intentionally not part of the current architecture.

Lint output has two different meanings:

- Hard/verifiable defects, such as broken references, invalid configuration, missing
  required structures, budget violations, deterministic duplication, and invalid document
  relationships. These are suitable for blocking CI when configured.
- Risk signals, such as clarity concerns, possible semantic duplication, possible
  contradiction, excessive context, and weak hierarchy. These justify review or
  escalation to stronger evidence, but they are not proof of agent failure.

## Command Map

| Command | Purpose | Evidence | External model required |
|---|---|---|---|
| `ai-doc check .` | Analyze discovered documentation | A0, optional A1 | No |
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

The fake target is executed with `examples/target-probe` as its working directory, so the command names `fake_target.py` directly.

## Discovery And Profiles

`ai-doc` automatically recognizes a conservative set of common AI-documentation conventions, including well-known instruction files, skill locations, and agent-specific rule formats.

Additional Markdown files and globs can be included through `.ai-doc.yaml`. This allows project-specific documentation such as architecture notes, domain knowledge, internal references, or custom instruction files to participate in analysis without requiring a built-in convention.

Discovery determines which documents belong to an analysis run. Profiles describe the role those documents play:

- `instruction`: high-priority behavioral or operational guidance;
- `skill`: task-specific procedural guidance;
- `reference`: supporting documentation and context;
- `adr`: architecture decision material;
- `generic`: fallback documentation without a more specific role.

Known conventions can receive built-in discovery and profile defaults. Repository-specific Markdown can use the same profiles through project configuration.

Discovery and classification do not prove how or when a real external AI runtime loads a document:

```text
document discovered
        |
profile / metadata interpreted
        |
configured or approximated context behavior
        !=
observed target-runtime behavior
```

Effective-context selection used by semantic evaluation and probes is deterministic and auditable, but remains an approximation unless stronger behavioral evidence is supplied by a C-tier target adapter.

`loading` configuration describes the project's modeled loading behavior for analysis and cost estimation; it does not discover real runtime load frequency.

See [Configuration](docs/guides/configuration.md) and [Analysis Pyramid](docs/design/analysis-pyramid.md) for detailed discovery, profile, loading, and evidence semantics.

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

- `include`, `exclude`, `profiles`, `loading`, and `extensions` accumulate with paths scoped relative to the nested config directory.
- `budgets`, `pricing`, and `evaluation` merge like dictionaries.
- named process-extension capability mappings under `extension_runtime` follow the documented nested-configuration merge rules.
- `optimization` is replaced when a nested config explicitly sets it.
- An explicit `--config` file does not implicitly merge nested `.ai-doc.yaml` files.

Generated starter config stays concise. It includes user-facing discovery/profile defaults but does not serialize empty/default-only sections merely to mirror every Pydantic field.

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

For process-backed extensions, configuration maps logical component names to commands under `extension_runtime`.

The extension system supports:

- analyzers;
- finding adapters;
- evaluators;
- token counters;
- recommendation policies;
- semantic providers.

Process-backed implementations speak the shared `ai-doc.extension/v1` stdin/stdout protocol. `components` and mode-specific evaluator configuration select which named implementations affect production behavior.

Process extension infrastructure failures, such as command startup failure, timeout, invalid protocol JSON, schema validation failure, or explicit protocol error responses, are reported as concise CLI errors with exit code `1` for `check`, `optimize`, `probe`, and `execute`; normal mode does not print Python tracebacks.

Details live in [Extension Runtime Configuration](docs/guides/extension-runtime-configuration.md) and [Extension API](docs/guides/extensions.md).

## Examples

The examples are executable and covered by deterministic CI:

- [basic](examples/basic/README.md): minimum A0 static workflow.
- [extensions](examples/extensions/README.md): process-backed extension runtime example.
- [conflicting-instructions](examples/conflicting-instructions/README.md): known deterministic findings.
- [hierarchical-config](examples/hierarchical-config/README.md): nested config merge and scoping semantics.
- [semantic](examples/semantic/README.md): optional A1 local semantic analysis.
- [multi-agent](examples/multi-agent/README.md): coexistence of major agent ecosystems.
- [target-probe](examples/target-probe/README.md): deterministic C1/C2 fake target.

## Optional Local Semantic ML

A1 local semantic analysis uses locally provisioned sentence-transformer/NLI models:

```bash
python -m pip install -e ".[ml]"
```

Normal `ai-doc check` runs do not silently download models. Configure `local_ml` explicitly and provide local model artifacts through explicit paths, `AI_DOC_MODEL_ROOT`, a local cache, or a packaged model bundle.

See [Analysis Pyramid](docs/design/analysis-pyramid.md) and [Packaging](docs/operations/packaging.md).

## Optional Predictive Evaluation

`ai-doc optimize` and `ai-doc check --deep` can use optional evaluator/provider
integrations for B-tier predictive evidence.

Promptfoo and DeepEval remain optional evaluation engines. Promptfoo has two supported
`ai-doc` modes:

- lexical mode, the compatibility default, uses Promptfoo `echo` plus
  `contains`/`not-contains` assertions and is not semantic evidence;
- model-graded mode is explicit, requires a configured Promptfoo model, and delegates
  semantic rubric grading to Promptfoo.

DeepEval also requires an explicit model. Deep evaluation budgets can cap known
requests, input tokens, output tokens, and USD usage. When a backend cannot report token
or cost data reliably, `ai-doc` marks those dimensions unknown instead of inventing them.
Provider-backed semantic optimization uses the provider-neutral
`AI_DOC_SEMANTIC_COMMAND` contract.

See [Semantic Optimization](docs/guides/semantic-optimization.md) and [Predictive Semantic Evaluation](docs/design/predictive-evaluation.md).

## Why Not Use Promptfoo Or DeepEval Directly?

Promptfoo and DeepEval are evaluation engines. `ai-doc` adds repository/document-domain
concerns around them: Markdown discovery, profiles and scope, context loading models,
documentation graph analysis, static checks, invariant preservation, token and cost
analysis, evaluator-independent scenarios, budget and escalation policy, normalized
results, and real-agent probes.

Use Promptfoo or DeepEval directly when you only need to test a small set of stable
prompts. `ai-doc` becomes useful when AI-facing documentation is a system: several
instruction files, skills, reference docs, agent ecosystems, budgets, and release gates.
A project with one small instruction file, few stable prompts, and no multi-agent
documentation structure may not need `ai-doc`.

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

C2 uses a temporary workspace copy and independently records filesystem deltas. This is workspace isolation, not an OS sandbox.

See [Behavioral Evaluation](docs/design/behavioral-evaluation.md) and [Execution Probes](docs/design/execution-probes.md).

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
- documented project-local extensions for analyzers, finding adapters, evaluators, token counters, recommendation policies, and semantic providers;
- explicit exports from `ai_doc.api.v1`.

Internal optimizer, parser, storage, Promptfoo, DeepEval, provider, local-ML adapter, target-command adapter, and GEPA modules are not extension contracts.

## Documentation

Use these when you want to run or configure the tool:

- [Getting Started](docs/guides/getting-started.md): install modes, first run, and common commands.
- [Runbook](docs/operations/runbook.md): routine operation, CI usage, diagnosis, and recovery.
- [Configuration](docs/guides/configuration.md): `.ai-doc.yaml`, discovery, profiles, budgets, loading, evaluation, optimization, and extensions.
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

- [Extension API](docs/guides/extensions.md): stable `ai_doc.api.v1` imports and extension contracts for analyzers, evaluators, token counters, recommendation policies, and semantic providers.
- [Extension Runtime Configuration](docs/guides/extension-runtime-configuration.md): process-backed capability configuration and runtime behavior.
- [Packaging](docs/operations/packaging.md): source checkout, wheel, executable builds, checksums, local model bundles, and limitations.
- [Release Notes](docs/operations/release-notes.md): user-visible changes by version.
- [Deferred Work](docs/design/deferred.md): intentionally postponed capabilities and known limitations.

## Exit Codes

- `0`: success or no blocking findings.
- `1`: internal, tool, configuration, or extension infrastructure error.
- `2`: static quality gate failed.
- `3`: semantic evaluation gate failed.
- `4`: optimization produced no acceptable candidate.
