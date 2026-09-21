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

A dedicated `Security` workflow runs `python -m pytest tests/security` for causal
security regression coverage. Keep this check failing on regressions; do not mark it
advisory for extension trust, provider selection, process environment, probe evidence,
or workspace isolation contracts.

Workflow path filters may skip ordinary guide/release-note documentation where useful,
but they must not blanket-ignore Markdown. Control-plane files such as `AGENTS.md`,
`CLAUDE.md`, `.ai/**`, `.codex/**`, `.claude/**`, `.github/**`, and
`docs/standards.md` must continue to trigger relevant checks.

GitHub-maintained first-party Actions may remain on version tags for this release.
Immutable commit SHA pinning is recommended defense in depth rather than a `0.2.0`
blocker for those Actions. New third-party Actions should use a full commit SHA with a
human-readable version comment unless a PR documents why that is not practical.

Executable builds should run on native OS runners. Do not add unsupported
cross-compilation.

## Release Checklist

1. Run default verification.
2. Run `python -m pytest tests/security`.
3. Run wheel smoke.
4. Run executable smoke on each release platform and extras mode being published.
5. Confirm `ai-doc doctor` in executable mode reports `standalone executable`.
6. Confirm missing deep-evaluator dependencies return exit code `3`.
7. Confirm checksums exist for executable artifacts.
8. Update [Release Notes](release-notes.md) with user-visible behavior and public
   contract changes.
9. Publish wheel/sdist and executable artifacts with checksums.
