# Project Standards

This document defines normative standards for `ai-doc`.

Use this page when changing implementation, tests, public behavior, or documentation.
Unlike the getting-started guide, this page is intentionally strict: it tells contributors
what must remain true so the tool stays predictable for users.

Terms used here:

- Public contract: behavior users can rely on across releases.
- Optional integration: a tool such as Promptfoo or DeepEval that is useful but not
  required for static checks.
- Target repository: the project whose Markdown documentation `ai-doc` is analyzing.

## Public Contract Standards

- Public Python imports must be exported from `ai_doc.api.v1`.
- Internal modules must not be documented as extension import targets.
- CLI commands, documented options, exit codes, JSON schemas, config schema, and extension
  registration are stable public contracts.
- Breaking public contracts requires an explicit versioned migration path.

## CLI Standards

- Human output goes to stdout in console mode.
- JSON mode must not print unrelated human text to stdout.
- Diagnostics may use stderr.
- External tool exit codes must be normalized to `ai-doc` exit codes.
- Static mode must not require optional external tools or API keys.
- Commands should accept project paths and `--root` where root discovery matters.

Stable exit codes:

- `0`: success / no blocking findings.
- `1`: internal, tool, or configuration error.
- `2`: static quality gate failed.
- `3`: semantic evaluation gate failed.
- `4`: optimization produced no acceptable candidate.

## Configuration Standards

- `.ai-doc.yaml` is the canonical project configuration file.
- Unknown top-level config keys should fail validation unless intentionally reserved.
- Configuration models must use typed Pydantic schemas.
- Default excludes must skip generated output and source-checkout `ai-doc` tool files.
- Nested `.ai-doc.yaml` files must be scoped to their containing directory.
- Explicit `--config` runs must not implicitly merge nested configs.
- Pricing must be data driven; do not hardcode live model prices.
- Missing load probabilities or pricing must produce unknown estimates, not invented
  values.

## Extension Standards

- Extensions must be explicitly configured.
- Extension paths must stay inside the project root.
- Extensions register behavior through `register(registry)`.
- The registry validates registrations and reports actionable errors.
- Extension examples must import from `ai_doc.api.v1`.
- Extension loading executes code; document trust requirements wherever extensions are
  described.

## Architecture Standards

- Core domain models must not import Typer.
- Core domain models must not expose Promptfoo or DeepEval result structures.
- Structural optimization must not depend directly on DeepEval.
- LLM providers must remain replaceable behind protocols.
- Source repository files must not be mutated during optimization.
- Findings and evaluation results must use stable machine-readable schemas.
- FinOps, clarity, reliability, and critical invariant recall must remain separate
  dimensions.
- Semantic success and invariant preservation dominate token reduction.

## Python Code Standards

- Prefer existing patterns before introducing new abstractions.
- Use objects where they own state, configuration, or replaceable behavior.
- Keep pure calculations as functions when a class adds no useful responsibility.
- Use `pathlib.Path`, `tempfile`, `shutil`, and `importlib.resources` for filesystem and
  resource work.
- Avoid `os.system`.
- Avoid `subprocess(..., shell=True)` unless there is a documented reason.
- Prefer `subprocess.run([...], shell=False)`.
- Keep optional imports inside adapters when dependencies are optional.
- Add comments only where they clarify non-obvious behavior.

## Analyzer Standards

- Finding codes must be stable and machine-readable.
- Deterministic analyzers must not claim semantic certainty they cannot prove.
- Heuristics should report evidence and actionable suggestions.
- Profile-specific recommendations must respect profile purpose. ADRs and reference docs
  should not be compressed merely because they are long.

## Optimization Standards

- Generate structured proposals before rendering Markdown candidates.
- Run cheap deterministic gates before expensive evaluation.
- Reject candidates with critical invariant regressions.
- Include baseline in Pareto comparison.
- Do not collapse objectives into one weighted scalar for frontier membership.
- Store candidate lineage and run metadata.
- Preserve full candidate history even when candidates are dominated.

## Packaging Standards

- Source checkout mode must remain editable.
- Standalone executable mode is an optional distribution artifact, not the only supported
  workflow.
- Build logic belongs in cross-platform Python, not substantial shell scripts.
- Executable builds must generate SHA-256 checksums.
- Promptfoo must remain optional, Python-installable through extras, and runtime-discovered.
- Package-owned resources must load in source, wheel, and executable modes.

## Testing Standards

- Unit tests must not require live API credentials.
- External LLM, Promptfoo, DeepEval, and GEPA calls must be mockable.
- Default test suite should be fast and deterministic.
- Heavy wheel/executable smoke tests may be opt-in but must be documented.
- Tests should cover Windows-style paths, POSIX-style assumptions where possible,
  spaces/unicode paths, root discovery, extension loading, resources, and runtime mode.

## Documentation Standards

- README is an entry point, not the full manual.
- Detailed docs live under `docs/`.
- General documentation-writing guidance lives in `docs/AGENTS.md` so human maintainers
  can apply it manually.
- Agent-only procedural workflows belong in `.ai/skills/`, with Codex and Claude adapters
  under `.codex/skills/` and `.claude/skills/`.
- Operational procedures belong in `docs/operations/runbook.md`.
- Normative project rules belong in this standards document.
- Architecture rationale belongs in `docs/design/architecture.md` and `docs/design/decisions.md`.
- Deferred work belongs in `docs/design/deferred.md`.
