---
name: "ai-doc-packaging-maintenance"
description: "Maintain ai-doc packaging, source-checkout bootstrap, wheel behavior, executable builds, and runtime detection without mixing target-project dependencies into the tool runtime."
version: 1
---

# ai-doc Packaging Maintenance

Use this skill when changing build, bootstrap, launcher, wheel, executable, packaged
resource, or runtime-mode behavior.

## Required Context

Read these first:

- `docs/operations/packaging.md`
- `docs/operations/testing-and-release.md`
- `docs/standards.md`

Read `docs/design/architecture.md` before changing module boundaries or adapter
responsibilities.

## Instructions

- Keep source-checkout mode usable from `.tools/ai-doc/`.
- Keep `tools/bootstrap.py` as cross-platform Python that creates a tool-owned runtime.
- Do not touch target-project dependency files such as `package.json`, `composer.json`,
  `go.mod`, `*.csproj`, or `pom.xml`.
- Keep launchers thin; business logic belongs in Python modules.
- Keep package-owned resources loadable from source, wheel, and executable modes through
  robust package-resource loading.
- Keep Promptfoo, DeepEval, and GEPA optional. Missing optional integrations must not
  break static `check`.
- Use cross-platform filesystem and subprocess APIs. Prefer `pathlib`, `shutil`,
  `tempfile`, and `subprocess.run([...], shell=False)`.
- Preserve the canonical executable build command:

```bash
python -m tools.build executable
```

## Validation

For packaging changes, run the normal repository checks and the relevant smoke tests:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
$env:AI_DOC_RUN_WHEEL_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_packaging_smoke.py::test_wheel_build_install_smoke
$env:AI_DOC_RUN_EXECUTABLE_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\integration\test_packaging_smoke.py::test_executable_smoke
```

If a smoke test cannot run locally, report the reason and leave the documented command.
