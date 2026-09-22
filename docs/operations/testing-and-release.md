# Testing And Release

Use this page when validating code changes, checking packaging artifacts, or preparing a
release. For everyday tool usage, start with [Getting Started](../guides/getting-started.md).

## Default Verification

Run these before considering a change complete:

```bash
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
```

On POSIX:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest
.venv/bin/python -m mypy
```

## CLI Smoke

CLI smoke tests exercise the installed command in realistic ways. They are useful after
packaging changes, command-line option changes, or root-discovery changes.

```bash
ai-doc --version
ai-doc version
ai-doc doctor examples/basic
ai-doc doctor examples/basic --format json
ai-doc check examples/basic --allow-extensions
ai-doc optimize examples/basic --strategy balanced --show-frontier
```

Nested root discovery smoke:

```bash
cd examples/basic/docs
ai-doc check --format json
```

Deep-mode unavailable smoke:

```bash
ai-doc check examples/basic --deep --non-interactive
```

If the configured deep evaluator is missing, expected public behavior is exit code `3`
with an actionable message. To verify automatic setup, run:

```bash
ai-doc check examples/basic --deep --install-missing
```

## Packaging Smoke

Wheel smoke:

```bash
AI_DOC_RUN_WHEEL_SMOKE=1 python -m pytest tests/integration/test_packaging_smoke.py::test_wheel_build_install_smoke -q -s
```

Executable smoke:

```bash
AI_DOC_RUN_EXECUTABLE_SMOKE=1 python -m pytest tests/integration/test_packaging_smoke.py::test_executable_smoke -q -s
```

These tests are opt-in because they build installable artifacts and may take longer than
the default suite.

When releasing an executable with optional deep integrations, also build and smoke-test
the selected extras mode:

```bash
python -m pip install -e ".[deep]"
python -m tools.build executable --extras deep
dist/windows-x64/ai-doc.exe doctor examples/basic
```

## CI

The GitHub Actions workflow runs on Windows, Linux, and macOS with Python 3.12:

- install;
- Ruff;
- mypy;
- pytest;
- wheel smoke;
- CLI smoke.

A dedicated `Security` workflow provides blocking checks for the project trust
boundaries:

- `Security / contracts` runs `python -m pytest tests/security` for causal security
  contracts. Keep this check failing on regressions; do not mark it advisory for
  extension trust, provider selection, process environment, probe evidence, workspace
  isolation, or security tooling/routing contracts.
- `Security / static` runs `python -m bandit -r src --severity-level medium
  --confidence-level medium` against production Python code. Bandit is a
  suspicious-pattern scanner, not proof that the trust model is safe. Low-severity
  heuristic findings remain review signals instead of merge blockers. Medium/high
  findings should be inspected, reviewed against [Security Standards](../standards.md),
  and suppressed only with narrow `# nosec Bxxx` annotations carrying a useful reason.
- `Security / dependencies` runs `python -m pip_audit --local --cache-dir .pip-audit-cache`
  after installing the repository's development dependency set. The explicit cache path
  keeps local and CI runs inside the workspace. Known-vulnerability exceptions must be
  narrow, named by advisory and dependency, and include a review or expiration condition.
The dedicated mutation workflow runs the single authoritative `mutmut` scope. The
mutation configuration includes security-sensitive decisions such as extension
authorization, authoritative finding preservation, explicit GEPA model requirements,
process environment forwarding, probe evidence cross-checks, and workspace symlink
rejection.

Security contracts prove project-specific invariants. Bandit reports suspicious Python
patterns. `pip-audit` reports known dependency vulnerabilities. Mutation testing asks
whether tests would fail if a security decision were weakened. No one layer replaces the
others.

Workflow path filters may skip ordinary guide/release-note documentation where useful,
but they must not blanket-ignore Markdown. Control-plane files such as `AGENTS.md`,
`CLAUDE.md`, `.ai/**`, `.codex/**`, `.claude/**`, `.github/**`,
`docs/standards.md`, `docs/design/**`, and
`docs/operations/testing-and-release.md` must continue to trigger relevant checks.
For `0.2.0`, the primary workflows intentionally keep broad Markdown triggering and skip
only ordinary guide pages plus release notes. This conservative choice keeps required
checks reliable for control-plane Markdown even though some ordinary documentation
changes may run more validation than strictly necessary.

GitHub-maintained first-party Actions may remain on version tags for this release.
Immutable commit SHA pinning is recommended defense in depth rather than a `0.2.0`
blocker for those Actions. New third-party Actions should use a full commit SHA with a
human-readable version comment unless a PR documents why that is not practical.

Executable builds should run on native OS runners. Do not add unsupported
cross-compilation.

## Release Checklist

1. Run default verification.
2. Run `python -m pytest tests/security`.
3. Run `python -m bandit -r src --severity-level medium --confidence-level medium`.
4. Run `python -m pip_audit --local --cache-dir .pip-audit-cache`.
5. Run the authoritative mutation workflow scope and review any surviving
   security-relevant mutants.
6. Run wheel smoke.
7. Run executable smoke on each release platform and extras mode being published.
8. Confirm `ai-doc doctor` in executable mode reports `standalone executable`.
9. Confirm missing deep-evaluator dependencies return exit code `3`.
10. Confirm checksums exist for executable artifacts.
11. Update [Release Notes](release-notes.md) with user-visible behavior and public
   contract changes.
12. Publish wheel/sdist and executable artifacts with checksums.
