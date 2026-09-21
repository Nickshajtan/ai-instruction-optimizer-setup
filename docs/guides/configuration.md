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
- Which documents should be treated as instructions, skills, references, or other
  profiles for `ai-doc` analysis?
- Which optional evaluators, optimizers, budgets, components, and extensions are enabled?

## Minimal Configuration

```yaml
version: 1
include:
  - AGENTS.md
  - CLAUDE.md
  - ".ai/**/*.md"
  - ".codex/**/*.md"
  - ".claude/**/*.md"
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
  ".ai/skills/**/SKILL.md": skill
  ".codex/skills/**/SKILL.md": skill
  ".claude/skills/**/SKILL.md": skill
  "docs/**": reference
```

If no config exists, built-in defaults are used for basic operation. `ai-doc init`
creates a starter config and `.ai-doc/evals/basic.yaml`.

## Include And Exclude

`include` controls Markdown discovery. `exclude` removes matching files from discovery.
Patterns are evaluated relative to the project root and results are sorted
deterministically.

Use `include` for files that belong to the repository's agent-facing documentation
interface, such as `AGENTS.md`, `CLAUDE.md`, `.ai/**/*.md`, `.codex/**/*.md`,
`.claude/**/*.md`, or `docs/**/*.md`. Discovery and parsing do not prove that a specific
external runtime loads those files. Use `exclude` for dependency folders, build output,
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
nested configs or inherit omitted fields from the root config. This keeps ad hoc and CI
runs reproducible. If the effective explicit config has `observability.enabled: false`
or omits the `observability` block, commands print a concise stderr warning that no
observation record will be written for that run. The warning does not change exit codes
and does not enable telemetry.

## Profiles

Supported profiles are `ai-doc` analysis categories:

- `instruction`: files treated as root or high-priority instructions for analysis, such
  as `AGENTS.md`.
- `skill`: agent skill documentation that may be routed into context on demand.
- `reference`: normal reference documentation.
- `adr`: architecture decision records.
- `generic`: fallback when no profile matches.

Profiles influence analyzer recommendations. For example, large examples are more
strongly discouraged in `instruction` docs than in `reference` docs.

The profile does not move files, change their content, or prove runtime loading behavior.
It tells analyzers how strict to be. An `instruction` file is treated as expensive because
it may be loaded on every task in the modeled context, while a `reference` file can be
longer because it is usually routed only when needed.

`skill` has one additional structural meaning: skill files are treated as independently
discoverable by an agent/runtime skill mechanism. A skill with no inbound Markdown links
is therefore not reported as `STRUCTURE_ORPHANED_AI_DOC` merely because the Markdown graph
does not link to it. Ordinary instruction files can still be reported as orphaned when
they have no inbound Markdown route and no independent discovery semantics.

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

Token budgets are model-agnostic policy thresholds. By default, `ai-doc` uses its own
deterministic approximate counter so static checks behave the same regardless of whether
a project uses OpenAI, Anthropic, local models, or several providers.

Budgets are guardrails, not billing data. They help identify files that are probably too
large for their role. Set lower budgets for always-loaded instruction files and looser
budgets for reference documents. Do not treat these numbers as exact provider-token
counts unless you have selected a counter that is exact for the provider and model you
care about. Check reports include both the selected `token_counter` and
`token_count_accuracy` so CI output can distinguish estimated, exact, mixed, and unknown
token-count evidence.

## Loading And Pricing

`loading` declares the project loading model that `ai-doc` should use for analysis and
cost estimation. It can mark files as always loaded or provide explicit load
probabilities.

```yaml
loading:
  AGENTS.md:
    mode: always
  docs/testing.md:
    mode: on_demand
    probability: 0.15
```

`pricing` is optional, user-supplied model metadata. The tool does not retrieve current
model prices and does not hardcode live prices.

```yaml
pricing:
  claude-sonnet:
    input_per_million: 3.00
    output_per_million: 15.00
```

If load probabilities or prices are absent, expected token or cost fields remain unknown.

Use `loading` when you want to declare how often a document is expected to enter agent
context. `ai-doc` does not discover real load frequency from that setting, and a
configured probability is a project policy input rather than an observed runtime fact.
`loading.mode: on_demand` models context-loading frequency and cost. It does not, by
itself, assert that a document is independently runtime-discoverable for orphan analysis.
Use `pricing` only when you intentionally want model-specific cost estimates and you are
prepared to maintain the model price values yourself. If you do not know, leave these
fields out. `ai-doc` will report unknown cost estimates instead of inventing numbers.

Current static findings do not need pricing. They use the selected token counter to
compare documentation size, always-loaded context, duplication, and budget pressure. The
default `approximate` counter is provider-neutral estimated evidence; Claude-oriented
projects do not need to treat OpenAI or tiktoken tokenization as authoritative.

Effective-context selection for semantic evaluation and probes starts from profiles and
explicit routes in already reachable context. That selection is deterministic and
auditable, but it approximates target-agent loading; it is not a runtime-specific Claude,
Codex, Copilot, Cursor, or Gemini loader.

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

DeepEval-backed evaluation requires an explicit model:

```yaml
evaluation:
  deep:
    engine: deepeval
    model: gpt-4o-mini
```

If `engine: deepeval` is selected without `model`, `ai-doc` exits with a configuration
error instead of allowing DeepEval to choose an implicit OpenAI default.

Use static checks first. Add deep evaluation when you need to test whether documentation
actually supports a realistic task, such as routing an agent to the right runbook or
preserving a safety requirement during optimization.

## Optimization

```yaml
optimization:
  engine: deepeval
  deepeval_model: gpt-4o-mini
  pairwise_semantic: false
  gated_pairwise: false
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
    reflection_model: null
    mutation_model: null
```

CLI options can override common search settings:

```bash
ai-doc optimize . --candidates 6 --generations 3 --max-candidates 12
ai-doc optimize . --max-cost 1.00 --max-requests 20 --seed 42
```

`ai-doc optimize` protects tool-owned optimization output from re-entering optimization
source discovery. The default `.ai-doc-output/**` tree, and a custom in-project
`--output` tree for that run, are excluded from optimization inputs even if an explicit
config uses broad includes such as `"**/*.md"` and omits the default exclude. This is an
optimizer ownership boundary, not generic Markdown discovery behavior.

The optimization settings bound how many candidates are generated, how much search is
allowed, and what trade-offs are acceptable. Keep defaults until you have reviewed a few
optimization reports and understand which limits matter for your workflow.

`pairwise_semantic` is an explicit opt-in B-tier confidence layer. It compares baseline
and candidate documentation for predicted instruction-following quality and records
`candidate`, `baseline`, `equivalent`, or `uncertain` evidence. It is not measured
Claude/Codex task success; static and invariant checks remain the authoritative hard
constraints, and unavailable or uncertain pairwise evidence does not fail optimization.
When pairwise evaluation falls back to DeepEval instead of a configured semantic
provider, `optimization.deepeval_model` must be set so no implicit provider/model is
selected.

Pairwise judging only runs for candidates that survive earlier gates. Reports expose
`run.pairwise_semantic_requested`, `run.pairwise_comparisons_performed`, and
`run.pairwise_comparisons_skipped_not_needed` so automation can distinguish "not
requested", "requested but no candidate reached B-tier", and "requested but optional
judging was intentionally unnecessary."

`gated_pairwise` is an opt-in shortcut for optional pairwise judging. When enabled,
`ai-doc` skips pairwise for a candidate that already has non-pairwise objective evidence
sufficient for the recommendation material-improvement rule. It does not weaken static
checks, invariant verification, semantic evaluation, GEPA re-gating, recommendation
thresholds, or budget enforcement. Use `ai-doc optimize --gated-pairwise` for a single
run.

Use `ai-doc optimize --require-pairwise-semantic` when a run should fail unless at
least one pairwise comparison actually occurs. Strict pairwise overrides
`gated_pairwise`; an intentional optional skip never satisfies the required-pairwise
postcondition.

GEPA prompt suboptimization is disabled by default. When enabled through
`optimization.gepa.enabled`, `--gepa`, or `--experimental-gepa`, both
`optimization.gepa.reflection_model` and `optimization.gepa.mutation_model` must be set
explicitly. `ai-doc` does not infer GEPA models from installed packages, provider
credentials, DeepEval defaults, or hardcoded OpenAI model names.

## Local Observation Logging

Observation logging records one local JSONL record per opted-in command run. Use it when
dogfooding `ai-doc` and you want raw machine facts for later offline analysis of evidence
tier behavior, escalation, cost, latency, findings, and optimizer activity.

```yaml
observability:
  enabled: true
  path: .ai-doc/observations.jsonl
```

The default path is `.ai-doc/observations.jsonl`. Each line is an independent
`ai-doc.observation/v1` JSON object. Logging is append-only and local; `ai-doc` does not
upload observations or create a database.

Observation records are intended to contain structured machine facts such as command
status, duration, document counts, tier names, finding fingerprints, evaluation outcomes,
provider token/cost usage when reported, and optimizer counters. They are not human
feedback and do not infer whether a recommendation was useful, accepted, or fixed.

The observation layer avoids Markdown body text, prompts, full model responses, secrets,
environment variables, absolute repository paths, and raw subprocess output. Document
identity is represented with stable hashes for later comparison across runs. If writing
the observation file fails, the primary command result is preserved and a concise warning
is printed to stderr.

## Extensions

Extensions are explicit, project-local Python files configured with the `extensions` key.
Configured files must stay inside the project root because extension loading executes
Python code.

Configuration declares extension capabilities; it does not authorize them. Commands that
may execute project-local Python extensions or `extension_runtime` processes fail closed
unless the operator passes `--allow-extensions`.

Python extensions can register analyzers, finding adapters, evaluators, token counters,
recommendation policies, and semantic providers. Registering a component makes it
available; selecting a named component makes it affect a production path.

```yaml
components:
  token_counter: company
  recommendation_policy: company
  provider: company
evaluation:
  deep:
    evaluator: company
extensions:
  - path: .ai-doc/extensions/company.py
```

Select a token counter that matches the provider/model semantics you want to budget
against. `approximate` is the default estimated local counter. `openai-tiktoken` is an
explicit OpenAI/tiktoken-compatible option and reports mixed accuracy because it falls
back to estimation when tiktoken or a model encoding is unavailable. Claude-oriented
projects should select a Claude-appropriate Python or process token counter, or keep the
default estimated counter with that limitation understood.

`extension_runtime` configures process-backed components using the same names:

```yaml
components:
  token_counter: company-counter
  recommendation_policy: company-policy
  provider: company-provider
evaluation:
  deep:
    evaluator: company-evaluator
extension_runtime:
  analyzers:
    company-analyzer:
      command: [python, .ai-doc/extensions/company_process.py]
  token_counters:
    company-counter:
      command: [python, .ai-doc/extensions/company_process.py]
  evaluators:
    company-evaluator:
      command: [python, .ai-doc/extensions/company_process.py]
  recommendation_policies:
    company-policy:
      command: [python, .ai-doc/extensions/company_process.py]
  providers:
    company-provider:
      command: [python, .ai-doc/extensions/company_process.py]
```

Built-in names include `approximate` and `openai-tiktoken` for token counters,
`default` for the default recommendation policy, and `semantic-command` for the
`AI_DOC_SEMANTIC_COMMAND` provider when that environment variable is set. Evaluator
selection remains mode-specific through `evaluation.<mode>.evaluator`.

See [Extension API](extensions.md) for public imports, process operations, scope, and
trust rules.
