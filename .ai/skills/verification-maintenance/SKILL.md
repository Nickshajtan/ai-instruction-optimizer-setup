---
name: "ai-doc-verification-maintenance"
description: "Maintain ai-doc testing, CI, smoke checks, and release verification instructions without turning human docs into agent runbooks."
version: 1
---

# ai-doc Verification Maintenance

Use this skill when changing tests, CI, release checks, smoke-test commands, or validation
requirements.

## Required Context

Read these first:

- `docs/operations/testing-and-release.md`
- `docs/operations/runbook.md`
- `docs/standards.md`

Read `docs/operations/packaging.md` if the change affects wheel or executable smoke
tests.

## Instructions

- Keep the default test suite fast, deterministic, and free of live API credentials.
- Keep optional integration tests opt-in when they require external tooling, heavy build
  time, or platform-specific artifacts.
- Preserve coverage for root discovery, path portability, extension loading, package
  resources, optional dependency discovery, runtime mode detection, wheel smoke, and
  executable smoke.
- Keep CI matrix coverage for Linux, Windows, and macOS.
- Keep human docs explanatory. Put agent-only "before final answer" or task-specific
  verification workflow instructions in skills.
- When a required validation command cannot run, report the command and concrete reason.

## Standard Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
```

Packaging smoke commands:

```powershell
$env:AI_DOC_RUN_WHEEL_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_packaging_smoke.py::test_wheel_build_install_smoke
$env:AI_DOC_RUN_EXECUTABLE_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_packaging_smoke.py::test_executable_smoke
```
