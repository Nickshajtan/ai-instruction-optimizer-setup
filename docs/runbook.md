# Runbook

This runbook covers routine operation, diagnosis, and recovery for `ai-doc`.

Use this page after you know the basic commands and need repeatable procedures for local
work, CI, troubleshooting, or release checks. For a first-time walkthrough, use
[Getting Started](getting-started.md).

## Routine Static Check

Use static checks for frequent local or CI execution.

```bash
ai-doc check .
```

Expected behavior:

- No API keys are required.
- Promptfoo and DeepEval are not required.
- Exit code `0` means no blocking static errors.
- Exit code `2` means the static quality gate failed.

Use JSON in CI:

```bash
ai-doc check . --format json --non-interactive
```

Use `--non-interactive` in automation so a CI job never waits for a prompt.

## Deep Evaluation

Use deep checks when semantic behavior matters. Static checks can find structural and
clarity problems, but they cannot prove that documentation supports a realistic task.

```bash
ai-doc check . --deep
```

Expected behavior:

- Static checks always run first.
- The configured deep evaluator is read from `evaluation.deep.engine`.
- Promptfoo is discovered with executable lookup and Node.js version validation.
- DeepEval is discovered through Python importability.
- Raw Promptfoo result shapes are normalized to `ai-doc` evaluation schemas.
- Missing dependencies return exit code `3`.

Prepare optional dependencies up front:

```bash
python -m pip install "ai-doc[deep]"
ai-doc setup --deep
```

If you want setup to happen during the check, use:

```bash
ai-doc check . --deep --install-missing
```

Recovery for missing deep-evaluator dependencies:

1. Run `ai-doc check . --deep --install-missing`, or run `ai-doc setup --deep`.
2. If Promptfoo is configured, confirm `node --version` is at least `22.22.0`.
3. Confirm `promptfoo --version` works when using Promptfoo.
4. Rerun `ai-doc doctor`.
5. Rerun `ai-doc check . --deep`.

## Optimization

Default optimization is bounded and conservative enough for routine use.

```bash
ai-doc optimize .
```

Search modes:

- `conservative`: one candidate, compatible with v0.1 behavior.
- `balanced`: multiple first-generation candidates, Pareto selection, no iterative search.
- `search`: bounded iterative search from Pareto frontier parents.

Useful commands:

```bash
ai-doc optimize . --strategy conservative
ai-doc optimize . --strategy balanced --show-frontier
ai-doc optimize . --strategy search --generations 3 --max-candidates 12
```

After optimization:

1. Open `.ai-doc-output/<run-id>/report.json`.
2. Inspect `frontier.json` for non-dominated candidates.
3. Inspect the recommended candidate's `diff.patch`.
4. Apply the patch manually only after review.

`ai-doc` does not commit changes and does not modify source docs during optimization.

Treat optimization output as a proposal. Review the patch and candidate files before
copying changes back into source documentation.

## Doctor

Run:

```bash
ai-doc doctor .
ai-doc doctor . --format json
```

Doctor reports:

- package version;
- runtime mode;
- project root;
- configuration health;
- static analyzer availability;
- Python runtime;
- writable output status;
- Promptfoo availability;
- DeepEval importability;
- provider environment presence without secret values.

Use doctor first when a command fails in CI or in a packaged executable.

Doctor is read-only except for its temporary write probe under the project root. It does
not change project documentation or configuration.

## Root Discovery

If a command is run from a nested directory, `ai-doc` walks upward until it finds
`.ai-doc.yaml`.

```bash
cd repo/modules/foo/src
ai-doc check
```

Override discovery when needed:

```bash
ai-doc check --root /path/to/repo
ai-doc optimize --root /path/to/repo
ai-doc doctor --root /path/to/repo
```

## Common Failures

### Invalid Configuration

Symptom:

```text
Invalid ai-doc configuration
```

Action:

1. Check unknown top-level keys.
2. Validate profile names.
3. Validate numeric budgets and search limits.

### Broken Extension

Symptom:

```text
Failed to load extension:
.ai-doc/extensions/custom_rules.py
```

Action:

1. Confirm the path is inside the project root.
2. Confirm the file defines `register(registry)`.
3. Confirm registered analyzers provide `analyze(context)`.
4. Rerun with debug mode if stack details are needed.

### Packaged Executable Cannot See Promptfoo

Install Promptfoo with `ai-doc setup --deep` or add an existing Promptfoo executable to
`PATH` in the environment that runs the executable. Promptfoo still requires Node.js
22.22.0 or newer. Rerun `ai-doc doctor` after changing the environment.

### Optimization Produces No Recommended Candidate

Exit code `4` means no acceptable candidate was produced. Inspect:

- `report.json`;
- `frontier.json`;
- candidate `evaluation.json`;
- candidate `rejection_reasons`;
- `lineage.json`.

Likely causes:

- critical invariant regression;
- new static error;
- duplicate candidate fingerprint;
- failed required evaluation.
