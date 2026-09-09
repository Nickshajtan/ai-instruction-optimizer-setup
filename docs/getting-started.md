# Getting Started

`ai-doc` is a command-line tool that reviews Markdown files written for AI coding agents.
Examples include `AGENTS.md`, `CLAUDE.md`, coding-agent rules, project runbooks, and
reference docs that agents are expected to read while working.

The tool has two jobs:

- `check` reports documentation problems, such as unclear structure, risky instructions,
  duplicate context, and files that are expensive to keep loaded.
- `optimize` creates reviewable improvement candidates in a separate output directory.
  It does not edit your source Markdown files.

You do not need Promptfoo, DeepEval, API keys, or the target project's dependencies for
normal static checks.

## Before You Start

You need Python 3.12 or newer to run `ai-doc` from source or as an installed package.
For a standalone executable, the target project does not need Python.

Useful terms:

- Target project: the repository whose documentation you want to analyze.
- `ai-doc` checkout: the repository containing this tool.
- Static check: deterministic checks that run locally without LLM providers.
- Deep evaluation: optional semantic checks through Promptfoo or DeepEval.
- Source checkout mode: using `ai-doc` from a copy stored under another repository's
  `.tools/ai-doc` directory.

## Choose An Installation Mode

Use the mode that matches how you want to distribute the tool.

### Editable Install For Development

Use this mode when you are working on `ai-doc` itself or when Python tooling is acceptable.

From the `ai-doc` repository:

```bash
python -m pip install -e ".[dev]"
ai-doc --version
```

The `-e` flag means editable install. Changes you make in `src/ai_doc` are used without
reinstalling the package.

### Source Checkout Under A Target Project

Use this mode when a target project wants to vendor the tool source under `.tools/ai-doc`.
This keeps the target project's own dependencies untouched.

Expected layout:

```text
target-project/
|-- .ai-doc.yaml
|-- .ai-doc/
|   |-- evals/
|   `-- extensions/
`-- .tools/
    `-- ai-doc/
```

In this layout, `.ai-doc.yaml` is the target project's configuration, `.ai-doc/` stores
target-project evaluation scenarios and extensions, and `.tools/ai-doc/` is the vendored
copy of this tool. The default configuration excludes `.tools/ai-doc/**`, so broad
patterns such as `**/*.md` do not make the tool analyze its own documentation recursively.
See [Packaging](packaging.md#source-checkout-mode) for the detailed source-checkout
contract.

From `.tools/ai-doc`, create the tool environment:

```bash
python tools/bootstrap.py
```

This command runs `tools/bootstrap.py` as a direct script because bootstrap is the first
setup step for a raw checkout. It should work before `ai-doc` has been installed as a
package.

Run on POSIX:

```bash
./ai-doc check ../..
```

Run on Windows PowerShell:

```powershell
.\ai-doc.ps1 check ..\..
```

The `.venv` created by `tools/bootstrap.py` belongs to `ai-doc`, not to the target
project.

### Standalone Executable

Use this mode when a target project should not install Python packages.

Build from the `ai-doc` repository:

```bash
python -m tools.build executable
```

The dot in `tools.build` is Python module syntax. It means "run the `build.py` module from
the `tools` package." Build uses module execution because it runs after the checkout is
already usable, and module execution handles project imports more reliably. The final word,
`executable`, is an argument passed to the build module.

Run the Windows executable:

```bash
dist/windows-x64/ai-doc.exe --version
dist/windows-x64/ai-doc.exe doctor examples/basic
dist/windows-x64/ai-doc.exe check examples/basic
```

Executable names and output directories vary by operating system. See
[Packaging](packaging.md) for build details and smoke tests.

## Initialize A Project

Run `init` once in the target project to create starter configuration:

```bash
ai-doc init
```

This creates files only when they do not already exist. The important file is
`.ai-doc.yaml`, which tells `ai-doc` what Markdown files to analyze and how to classify
them.

A minimal configuration looks like this:

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
  "docs/**": reference
```

The `include` list selects Markdown files. The `exclude` list removes generated,
third-party, and tool-owned paths. The default `.tools/ai-doc/**` exclude prevents a
source-checkout copy of `ai-doc` from recursively analyzing its own documentation inside a
target project. The `profiles` section tells analyzers whether a file is an always-read
instruction file, a reference document, a skill, or another documentation type.

See [Configuration](configuration.md) for the full schema.

## Run Your First Check

Run a static check from the target project root:

```bash
ai-doc check .
```

You can also run from a nested directory. If `.ai-doc.yaml` exists above the current
directory, `ai-doc` walks upward to find the project root:

```bash
cd docs
ai-doc check
```

Use `--root` when you want to be explicit:

```bash
ai-doc check --root /path/to/repo
```

For a static check, no API keys are required. Promptfoo, DeepEval, and the target
project's dependencies are not required either. Exit code `0` means there were no
blocking static errors, while exit code `2` means the static quality gate failed.

For automation, use JSON output:

```bash
ai-doc check . --format json --non-interactive
```

## Understand Check Output

The check report includes:

- `files_analyzed`: how many Markdown files matched the configuration.
- `total_tokens`: approximate total documentation tokens.
- `profiles`: the profile assigned to each file.
- `context_cost`: token and context-cost estimates.
- `findings`: clarity, structure, risk, and FinOps findings.
- `evaluation`: deep-evaluation results when `--deep` is used.

Console output is meant for humans. JSON output is meant for CI, dashboards, and other
tools.

## Diagnose The Environment

Run `doctor` when setup behaves differently than expected:

```bash
ai-doc doctor .
ai-doc doctor . --format json
```

Doctor checks the package version, runtime mode, project root, configuration health,
Python runtime, writable output status, optional evaluator availability, and provider
environment variables without printing secret values.

## Optional Deep Evaluation

Static checks are the default. Deep evaluation is optional and uses the configured engine
from `.ai-doc.yaml`:

```yaml
evaluation:
  deep:
    engine: promptfoo
```

Supported deep engines are:

- `promptfoo`: runs Promptfoo through its CLI and normalizes the result.
- `deepeval`: imports DeepEval from Python and runs the DeepEval adapter.

Install both optional integrations through Python packaging:

```bash
python -m pip install "ai-doc[deep]"
ai-doc setup --deep
```

For editable development:

```bash
python -m pip install -e ".[deep]"
ai-doc setup --deep
```

Promptfoo caveat: the Python `promptfoo` package is a wrapper around the Node-backed
Promptfoo CLI. If `promptfoo` is selected, Node.js 22.22.0 or newer must be installed.

Run deep evaluation:

```bash
ai-doc check . --deep
```

If the configured evaluator is missing, install it during the check:

```bash
ai-doc check . --deep --install-missing
```

In interactive console mode, `ai-doc check --deep` can ask before installing missing
optional dependencies. In non-interactive mode, use `--install-missing` explicitly.

## Generate Optimization Candidates

Use `optimize` when you want reviewable documentation improvements:

```bash
ai-doc optimize .
```

The optimizer writes candidate files and reports under `.ai-doc-output/<run-id>/`.
It never edits the source Markdown files in place.

Useful strategy options:

```bash
ai-doc optimize . --strategy conservative
ai-doc optimize . --strategy balanced --show-frontier
ai-doc optimize . --strategy search --generations 3 --max-candidates 12
```

`conservative` creates one low-risk candidate. `balanced` creates multiple candidates and
uses Pareto selection without iterative search. `search` performs bounded iterative search
from Pareto frontier parents.

The output directory looks like this:

```text
.ai-doc-output/<run-id>/
|-- run.json
|-- baseline/
|-- candidates/
|   `-- C001/
|       |-- proposal.json
|       |-- candidate/
|       |-- evaluation.json
|       `-- diff.patch
|-- frontier.json
|-- lineage.json
|-- search-memory.json
`-- report.json
```

Review the generated `diff.patch` and candidate files before applying anything to the
target project.

## Common Next Steps

After the first successful check:

1. Tune `.ai-doc.yaml` so `include`, `exclude`, and `profiles` match your documentation
   layout.
2. Add organization-specific analyzers only when the built-in findings are not enough.
3. Add deep-evaluation scenarios under `.ai-doc/evals/` when semantic behavior matters.
4. Run `ai-doc check . --format json --non-interactive` in CI.
5. Use `ai-doc optimize . --strategy balanced --show-frontier` to inspect improvement
   candidates.

For operational recovery and CI guidance, see [Runbook](runbook.md). For extension
examples, see [Extension API](extensions.md).
