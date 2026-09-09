# Packaging

`ai-doc` supports source checkout, Python package installation, and standalone executable
distribution.

Use this page when you need to decide how to ship `ai-doc` to other repositories or build
release artifacts. For day-to-day use, [Getting Started](../guides/getting-started.md) is enough.

The distribution modes solve different problems:

- Source checkout keeps the tool editable under a target repository.
- Editable install and wheel install fit Python-based developer environments.
- Standalone executable avoids requiring Python packages in the target project.

Wheel mode is separate because it is the normal Python packaging artifact used by `pip`,
private package indexes, and release automation. It is not another runtime behavior of the
tool. After installation, a wheel and an editable install both provide the same `ai-doc`
console command; the difference is how the code reaches the environment.

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

## Python Package Modes

Use Python package modes when the machine that runs `ai-doc` can have a Python
environment.

Editable development install:

```bash
python -m pip install -e ".[dev]"
```

Editable install points Python at the local source tree. Use it while changing `ai-doc`.

Build a wheel:

```bash
python -m build --wheel --no-isolation --outdir dist/wheel-smoke
```

Wheel install uses a built artifact:

```bash
python -m pip install dist/wheel-smoke/ai_doc-*.whl
```

The wheel includes:

- package code under `ai_doc`;
- `py.typed`;
- resource templates under `ai_doc/resources`;
- console script entry point `ai-doc`.

Optional Python integrations are selected with extras before installation:

```bash
python -m pip install "ai-doc[promptfoo]"
python -m pip install "ai-doc[deepeval]"
python -m pip install "ai-doc[deep]"
```

`promptfoo` installs the Python wrapper package, but Promptfoo remains Node-backed.
`deepeval` installs the Python DeepEval package. `deep` installs both optional Python
packages.

## Standalone Executable

Canonical command:

```bash
python -m tools.build executable
```

By default, the executable includes only core static-check dependencies. That is the
smallest and most predictable artifact.

Development one-folder build:

```bash
python -m tools.build executable --onedir
```

Executable with optional Python integrations:

```bash
python -m tools.build executable --extras promptfoo
python -m tools.build executable --extras deepeval
python -m tools.build executable --extras deep
```

The selected extra packages must already be installed in the build environment. For
example:

```bash
python -m pip install -e ".[deep]"
python -m tools.build executable --extras deep
```

`--extras promptfoo` includes the Python `promptfoo` wrapper package, not Node.js itself.
The resulting executable still needs Node.js 22.22.0 or newer available on the machine
that runs Promptfoo-backed deep evaluation.

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

Promptfoo remains Node-backed. There are two supported executable strategies:

- Build the core executable and let users run `ai-doc setup --deep` or
  `ai-doc check --deep --install-missing` in their environment.
- Build with `python -m tools.build executable --extras promptfoo` or `--extras deep` to
  collect the Python wrapper into the executable. Node.js is still external.

DeepEval and GEPA remain optional. For executable builds that should run DeepEval-backed
evaluation without installing Python packages later, build with `--extras deepeval` or
`--extras deep` and smoke-test that artifact on each release platform.

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

Manual deep executable smoke when optional packages are included:

```bash
python -m pip install -e ".[deep]"
python -m tools.build executable --extras deep
dist/windows-x64/ai-doc.exe doctor examples/basic
dist/windows-x64/ai-doc.exe check examples/basic --deep --non-interactive
```

## Known Limitations

- No cross-compilation.
- Node.js is not bundled in the executable, even with `--extras promptfoo`.
- DeepEval packaged compatibility must be smoke-tested per release target when included.
- PyInstaller output is generated state and should not be committed by default.
