# Packaging

`ai-doc` supports source checkout, installed Python package, and standalone executable
distribution.

Use this page when you need to decide how to ship `ai-doc` to other repositories or build
release artifacts. For day-to-day use, [Getting Started](getting-started.md) is enough.

The three distribution modes solve different problems:

- Source checkout keeps the tool editable under a target repository.
- Wheel or editable install fits Python-based developer environments.
- Standalone executable avoids requiring Python packages in the target project.

## Source Checkout Mode

Use this mode for editable `.tools/ai-doc` deployments.

```bash
python tools/bootstrap.py
```

Bootstrap creates `.venv` in the `ai-doc` checkout and installs the tool there. The target
project's dependency files are not touched.

Launchers:

- POSIX: `./ai-doc`
- Windows PowerShell: `.\ai-doc.ps1`

The launchers are thin dispatchers. Business logic stays in Python modules.

## Wheel And Editable Install

Editable development install:

```bash
python -m pip install -e ".[dev]"
```

Build a wheel:

```bash
python -m build --wheel --no-isolation --outdir dist/wheel-smoke
```

The wheel includes:

- package code under `ai_doc`;
- `py.typed`;
- resource templates under `ai_doc/resources`;
- console script entry point `ai-doc`.

Use wheel builds when distributing through Python packaging infrastructure. Use editable
installs when changing the source code locally.

## Standalone Executable

Canonical command:

```bash
python -m tools.build executable
```

Development one-folder build:

```bash
python -m tools.build executable --onedir
```

Output:

```text
dist/<platform>/
|-- ai-doc or ai-doc.exe
`-- ai-doc(.exe).sha256
```

Current platform directory naming:

- `windows-x64`
- `linux-x64`
- `linux-arm64`
- `macos-x64`
- `macos-arm64`

Builds are native-runner builds. Cross-compilation is not supported.

Native-runner means a Windows executable is built on Windows, a macOS executable on macOS,
and a Linux executable on Linux.

## PyInstaller Choice

PyInstaller is used because it provides:

- one-file and one-directory executable modes;
- bundled Python interpreter;
- good support for Typer/Pydantic applications;
- package data collection for `importlib.resources`;
- native Windows, Linux, and macOS builds;
- practical debugging with `--onedir`.

Alternatives considered:

- PEX and shiv are strong Python environment artifacts but still assume a compatible
  Python interpreter.
- Nuitka can produce native binaries but adds compiler complexity for this stage.

## Packaged Mode Optional Integrations

Promptfoo remains Node-backed, but can be installed through the Python `promptfoo` wrapper
with `ai-doc setup --deep` or `ai-doc check --deep --install-missing`. The executable
detects the Promptfoo command through `PATH` and verifies Node.js is new enough.

DeepEval and GEPA remain optional. They are isolated so static checks and local candidate
generation work even when DeepEval is not importable.

## Smoke Tests

Default tests skip heavy packaging smoke tests.

Smoke tests are quick end-to-end checks that confirm the built artifact starts and can run
basic commands. They are separate from the normal unit and integration test suite because
wheel and executable builds take longer.

Wheel smoke:

```bash
AI_DOC_RUN_WHEEL_SMOKE=1 python -m pytest tests/integration/test_packaging_smoke.py::test_wheel_build_install_smoke
```

Executable smoke:

```bash
AI_DOC_RUN_EXECUTABLE_SMOKE=1 python -m pytest tests/integration/test_packaging_smoke.py::test_executable_smoke
```

Manual executable smoke:

```bash
python -m tools.build executable
dist/windows-x64/ai-doc.exe --version
dist/windows-x64/ai-doc.exe doctor examples/basic
dist/windows-x64/ai-doc.exe check examples/basic
```

## Known Limitations

- No cross-compilation.
- Promptfoo and Node are not bundled in the executable.
- DeepEval packaged compatibility must be smoke-tested per release target.
- PyInstaller output is generated state and should not be committed by default.
