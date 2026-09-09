# Configuration

Project configuration lives at `.ai-doc.yaml`. Unknown top-level keys fail validation so
mistakes are visible.

Use this page when you need to tell `ai-doc` which Markdown files belong to a project,
how those files should be classified, and which optional evaluation or optimization
features are enabled. New users can start with `ai-doc init` and only return here when
the defaults do not match their repository layout.

## How Configuration Is Used

Every command starts by finding a project root and loading `.ai-doc.yaml` from that root.
If the file is missing, `ai-doc` uses built-in defaults so basic checks still work. When a
root config exists, `ai-doc` also discovers nested `.ai-doc.yaml` files below the root and
merges their explicit settings into the run.

The configuration answers four practical questions:

- Which Markdown files should be analyzed?
- Which paths are generated, vendored, or otherwise irrelevant?
- Which documents are always-read instructions versus reference material?
- Which optional evaluators, optimizers, budgets, and extensions are enabled?

## Minimal Configuration

```yaml
version: 1
include:
  - AGENTS.md
  - CLAUDE.md
  - "docs/**/*.md"
exclude:
  - node_modules/**
  - vendor/**
  - build/**
  - dist/**
  - .ai-doc-output/**
  - .tools/ai-doc/**
profiles:
  AGENTS.md: instruction
  CLAUDE.md: instruction
  docs/AGENTS.md: instruction
  docs/CLAUDE.md: instruction
  "docs/**": reference
```

If no config exists, built-in defaults are used for basic operation. `ai-doc init`
creates a starter config and `.ai-doc/evals/basic.yaml`.

## Include And Exclude

`include` controls Markdown discovery. `exclude` removes matching files from discovery.
Patterns are evaluated relative to the project root and results are sorted
deterministically.

Use `include` for files agents are expected to read, such as `AGENTS.md`, `CLAUDE.md`,
`.claude/**/*.md`, or `docs/**/*.md`. Use `exclude` for dependency folders, build output,
generated reports, and other paths that should not be reviewed as source documentation.
The default excludes skip `.tools/ai-doc/**` so a source-checkout copy of this tool does
not recursively analyze its own Markdown files inside a target project.

For repositories with inner modules, wildcard patterns in one root config are often
enough:

```yaml
include:
  - AGENTS.md
  - "modules/*/AGENTS.md"
  - "modules/*/docs/**/*.md"
profiles:
  AGENTS.md: instruction
  "modules/*/AGENTS.md": instruction
  "modules/*/docs/**": reference
```

This is the simplest approach when all modules follow the same layout.

## Nested Module Configs

Use nested `.ai-doc.yaml` files when modules have their own documentation layout. A nested
config is scoped to the directory that contains it. For example:

```text
repo/
|-- .ai-doc.yaml
`-- modules/
    `-- payments/
        |-- .ai-doc.yaml
        |-- AGENTS.md
        `-- docs/
            `-- guide.md
```

If `modules/payments/.ai-doc.yaml` contains:

```yaml
version: 1
include:
  - AGENTS.md
  - "docs/**/*.md"
exclude:
  - "docs/private/**"
profiles:
  AGENTS.md: instruction
  "docs/**": reference
```

`ai-doc` treats those paths as:

```yaml
include:
  - modules/payments/AGENTS.md
  - "modules/payments/docs/**/*.md"
exclude:
  - "modules/payments/docs/private/**"
profiles:
  modules/payments/AGENTS.md: instruction
  "modules/payments/docs/**": reference
```

Nested config discovery requires a root `.ai-doc.yaml`. If no root config exists, `ai-doc`
uses built-in defaults and does not scan the tree for module configs. Nested configs merge
only fields that are explicitly present in the nested file. That prevents omitted fields
from injecting default root patterns into every module. Exact and deeper profile rules are
applied before broad parent rules.

Paths in nested configs must stay inside the nested directory. Patterns such as
`../shared.md` are rejected because they make ownership unclear. Use the root config for
shared files outside a module.

When `--config` is passed, `ai-doc` uses that explicit config file only and does not merge
nested configs. This keeps ad hoc and CI runs reproducible.

## Profiles

Supported profiles:

- `instruction`: always-loaded agent instructions such as `AGENTS.md`.
- `skill`: on-demand agent skill documentation.
- `reference`: normal reference documentation.
- `adr`: architecture decision records.
- `generic`: fallback when no profile matches.

Profiles influence analyzer recommendations. For example, large examples are more
strongly discouraged in `instruction` docs than in `reference` docs.

The profile does not move files or change their content. It tells analyzers how strict to
be. An `instruction` file is expensive because an agent may load it on every task, while a
`reference` file can be longer because it is usually opened only when needed.

Put exact instruction-file entries before broad patterns such as `docs/**`. Profile
patterns are checked in order, so `docs/AGENTS.md` should be classified before the generic
documentation rule catches it.

## Budgets

```yaml
budgets:
  instruction:
    warning_tokens: 3000
    error_tokens: 6000
  skill:
    warning_tokens: 3500
  reference:
    warning_tokens: null
```

Token counts are approximate unless a model-aware counter is configured in future
versions.

Budgets are guardrails, not billing data. They help identify files that are probably too
large for their role. Set lower budgets for always-loaded instruction files and looser
budgets for reference documents.

## Loading And Pricing

`loading` can mark files as always loaded or provide explicit load probabilities.

```yaml
loading:
  AGENTS.md:
    mode: always
  docs/testing.md:
    mode: on_demand
    probability: 0.15
```

`pricing` is data driven. The tool does not retrieve current model prices.

```yaml
pricing:
  claude-sonnet:
    input_per_million: 3.00
    output_per_million: 15.00
```

If load probabilities or prices are absent, expected token/cost fields remain unknown.

Use `loading` and `pricing` only when you have enough information to estimate how often a
document is loaded and what model pricing applies. If you do not know, leave these fields
out. `ai-doc` will report unknown cost estimates instead of inventing numbers.

## Evaluation

```yaml
evaluation:
  fast:
    engine: promptfoo
  deep:
    engine: promptfoo
```

Evaluation scenarios live in `.ai-doc/evals/*.yaml`.

```yaml
id: testing-routing
profile: coding-task
task: |
  Fix a failing unit test.
expected:
  required:
    - run relevant validation
  forbidden:
    - modify generated files
tags:
  - testing
  - routing
```

Repository authors do not write raw Promptfoo YAML for normal use. The adapter maps
internal scenarios to Promptfoo configuration.

`evaluation.deep.engine` controls which evaluator `ai-doc check --deep` uses. Supported
values are `promptfoo` and `deepeval`. Missing optional dependencies can be prepared with
`ai-doc setup --deep` or `ai-doc check --deep --install-missing`.

Use static checks first. Add deep evaluation when you need to test whether documentation
actually supports a realistic task, such as routing an agent to the right runbook or
preserving a safety requirement during optimization.

## Optimization

```yaml
optimization:
  engine: deepeval
  strategy: balanced
  population:
    initial_candidates: 4
  search:
    generations: 1
    initial_candidates: 4
    children_per_generation: 3
    max_candidates: 4
    max_llm_requests: 100
    max_cost_usd: 5.00
    patience: 2
  pareto:
    tolerances:
      reliability: 0.01
      clarity: 0.01
      always_loaded_tokens: 100
      expected_context_tokens: 100
  recommendation:
    minimum_reliability_delta: -0.01
    minimum_clarity_delta: -0.02
  gepa:
    enabled: false
```

CLI options can override common search settings:

```bash
ai-doc optimize . --candidates 6 --generations 3 --max-candidates 12
ai-doc optimize . --max-cost 1.00 --max-requests 20 --seed 42
```

The optimization settings bound how many candidates are generated, how much search is
allowed, and what trade-offs are acceptable. Keep defaults until you have reviewed a few
optimization reports and understand which limits matter for your workflow.

## Extensions

Extensions are explicit, project-local checks configured with the `extensions` key.
Configured files must stay inside the project root because extension loading executes
Python code. See [Extension API](extensions.md) for the full example and trust rules.
