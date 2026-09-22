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
- CLI commands, documented options, exit codes, JSON schemas, config schema, and
  documented extension registration paths are stable public contracts.
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
- Repository-declared executable extensions must not execute unless the operator
  explicitly authorizes them with `--allow-extensions` on the command being run.
- Repository configuration must not be able to authorize its own executable extensions.
- Extension paths must stay inside the project root.
- In-process extensions register analyzer, finding-adapter, evaluator, token-counter,
  recommendation-policy, or semantic-provider behavior through `register(registry)`.
- The registry validates registrations and reports actionable errors.
- Extension examples must import from `ai_doc.api.v1`.
- Extension loading executes code; document trust requirements wherever extensions are
  described.
- Finding adapters may adapt the presented finding list, but the default CLI quality
  gate must preserve the existence of pre-adaptation built-in error findings.
- Process extensions must not inherit the full parent process environment by default;
  pass only the documented minimal runtime environment plus explicit configured values.

## Security Standards

- Repository-controlled content is untrusted input unless an independently trusted
  boundary explicitly grants it additional authority. This includes configuration,
  Markdown, nested configuration, extension declarations, executable paths, commands and
  arguments, provider/model identifiers, target-agent output, generated files, and
  external process responses.
- Configuration is not authorization. Repository-controlled configuration cannot
  independently authorize executable extensions, arbitrary process execution, external
  provider activation, access to credentials, elevated filesystem authority, or other
  privileged capabilities.
- Every security-sensitive change must identify the trusted actor, untrusted input,
  privileged operation, authorization boundary, validation boundary, failure behavior,
  and audit evidence. If these cannot be identified, do not invent implicit trust.
- Grant only the authority required for the operation. Review environment variables,
  credentials, filesystem access, network access, subprocess execution, writable
  locations, and inherited process state. Permission to execute is not permission to
  inherit every available capability.
- Security-sensitive ambiguity must fail closed with explicit rejection or explicit
  uncertainty rather than unsupported success.
- Do not silently activate external model/provider behavior based only on ambient
  credentials, installed packages, SDK defaults, implicit model defaults, or unrelated
  environment state. External execution and provider selection must follow explicit
  project configuration and authorization contracts.
- `shell=False` prevents shell interpretation, but it is not an authorization mechanism.
  Review who chooses the executable, who chooses arguments, who authorizes execution,
  which environment is inherited, which filesystem is accessible, which network authority
  exists, and which evidence is trusted afterward.
- External agents, providers, and subprocesses may return claims, but their self-report
  is not automatically authoritative. Security-sensitive conclusions must account for
  independent deterministic evidence where it exists, and must not claim semantic
  certainty beyond the evidence available.
- Isolation abstractions must enforce their own invariants, including symlink rejection,
  workspace boundaries, output boundaries, and writable paths. Do not rely on unrelated
  upstream operations accidentally enforcing those invariants.
- Extension mechanisms must not silently weaken authoritative built-in security or safety
  evidence. Any mechanism capable of suppressing, downgrading, replacing, or transforming
  authoritative findings requires explicit security review.
- Secrets and credentials must not be committed, written to ordinary diagnostics, included
  in observations, included in generated fixtures, exposed unnecessarily to child
  processes, or copied into security-test artifacts. Tests requiring secret-like data must
  use synthetic values.
- Every fixed vulnerability class must receive a causal regression test where practical:
  attacker-controlled input, production boundary, attempted security-sensitive effect,
  and protected result.
- Where a security guarantee depends on a conditional decision, mutation testing should
  be able to detect meaningful weakening of that decision. Do not require mutation
  testing for code that contains no meaningful security decision.
- Security-sensitive dependencies and CI automation must be reviewed proportionally to
  their authority. GitHub Actions should prefer first-party or well-established Actions,
  newly introduced third-party Actions should prefer immutable full-SHA references, and
  workflow permissions must remain least privilege. Avoid privileged workflow triggers
  unless required and reviewed.

## Architecture Standards

- Core domain models must not import Typer.
- Core domain models must not expose Promptfoo or DeepEval result structures.
- Structural optimization must not depend directly on DeepEval.
- LLM providers must remain replaceable behind protocols.
- Source repository files must not be mutated during optimization.
- Findings and evaluation results must use stable machine-readable schemas.
- GEPA must require explicit reflection and mutation model configuration when enabled;
  do not fall back to provider, credential, dependency, or hardcoded model defaults.
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
- Do not accept meaningful-looking domain/API parameters and immediately discard them.
  If a third-party callback requires an unused argument, make the compatibility reason
  explicit and narrowly scoped.
- Do not keep fake contract inputs for planned behavior. Wire them into behavior or remove
  them until the behavior exists.
- Domain-significant repeated strings (statuses, stop reasons, engine IDs, modes, severity
  values, protocol artifact names, cross-module metadata keys) must use typed/named domain
  values rather than scattered literals.
- Domain-policy numbers (thresholds, weights, tolerances, confidence cutoffs, extraction
  sizes, similarity limits, retry/generation limits) must be named or configured. Do not
  create constants for obvious indexes, zero/one structural values, or literals that are
  clearer inline.
- Broad text/regex transformations that encode product policy must have focused adversarial
  tests proving they do not corrupt unrelated Markdown structures.
- Do not introduce speculative Protocol/service/factory/strategy layers without a real
  external boundary, testing seam, domain dependency boundary, or multiple real behaviors.
- Broad `except Exception` handling belongs only at intentional plugin/provider/process
  boundaries and must preserve the original cause and actionable diagnostics.
- Comments, names, types, and reports must not claim semantic/deep/adaptive behavior that
  the implementation does not actually perform.

## Static Analysis Standards

- Ruff and strict mypy are required quality gates.
- Ruff configuration should incrementally enforce unused arguments (`ARG`), magic-value
  comparisons (`PLR2004`), and unused suppressions (`RUF100`) in addition to the existing
  rule set, with narrow per-file/local exceptions where an external interface requires it.
- Production optimizer/domain code must be checked for explicit deletion of meaningful
  function parameters (`del parameter`); use a small AST-based repository check rather
  than regex when generic lint rules cannot detect the misleading contract.
- Do not silence lint/type failures with broad repository-wide ignores. Exceptions must be
  local and justified by a concrete boundary or false positive.
- Dynamic optional-dependency adapters may use narrow `Any`/`cast` boundaries when the
  dynamic API cannot be represented safely and the boundary is tested.
- Static-analysis rules must target a demonstrated defect class; do not enable rules only
  to increase formal strictness.

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
- External LLM, Promptfoo, DeepEval, and GEPA calls must be replaceable with deterministic
  fakes at their boundary.
- Default test suite should be fast and deterministic.
- Heavy wheel/executable smoke tests may be opt-in but must be documented.
- Tests should cover Windows-style paths, POSIX-style assumptions where possible,
  spaces/unicode paths, root discovery, extension loading, resources, and runtime mode.
- Integration tests that claim optimizer correctness must assert domain outcomes, not only
  exit codes, file existence, candidate counts, or schema presence.
- A regression-test fixture must be capable of exposing the defect it claims to prevent.
  For example, baseline propagation needs non-empty baseline content and scenario isolation
  needs multiple scenarios with different expectations.
- Critical workflows require causal assertions showing that changing a meaningful input
  changes the downstream decision.
- Security-critical trust boundaries must have causal regression tests under
  `tests/security` and a dedicated failing CI check.
- Important happy paths should have negative/adversarial counterparts, especially around
  semantic evaluation, invariants, routing, budgets, and recommendation.
- Mock external boundaries rather than the implementation under test. Prefer deterministic
  fake providers over deep monkeypatch chains.
- Measure statement and branch coverage in CI. Coverage percentage is a guardrail, not
  proof of semantic correctness.
- Use a conservative repository-wide coverage threshold as a ratchet and prioritize
  stronger behavioral tests for optimizer/search, evaluators, invariants, generation,
  recommendation, budgets, and context routing.
- Mutation testing should target critical decision paths after the semantic-core vertical
  slice is implemented; do not optimize tests for a vanity mutation score.

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
- User-facing documentation must not promote an internal abstraction, configuration
  declaration, approximation, test adapter, or deferred capability into a stronger product
  capability without evidence from the production execution path.
- Ecosystem/runtime claims must distinguish file discovery and parsing support from
  runtime-behavior support, target-adapter observation, SDK/native integration, and
  deferred loaders.
