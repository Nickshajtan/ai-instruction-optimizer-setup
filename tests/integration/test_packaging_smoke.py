from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.getenv("AI_DOC_RUN_WHEEL_SMOKE") != "1",
    reason="Set AI_DOC_RUN_WHEEL_SMOKE=1 to run the wheel build/install smoke test.",
)
def test_wheel_build_install_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(dist)],
        cwd=root,
        check=True,
        shell=False,
    )
    wheel = next(dist.glob("ai_doc-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert "ai_doc/py.typed" in names
    assert "ai_doc/resources/default.ai-doc.yaml" in names
    assert any(name.endswith(".dist-info/entry_points.txt") for name in names)


@pytest.mark.skipif(
    os.getenv("AI_DOC_RUN_EXECUTABLE_SMOKE") != "1",
    reason="Set AI_DOC_RUN_EXECUTABLE_SMOKE=1 to run the heavier PyInstaller smoke test.",
)
def test_executable_smoke() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "-m", "tools.build", "executable"],
        cwd=root,
        check=True,
        shell=False,
    )
    exe_name = "ai-doc.exe" if sys.platform == "win32" else "ai-doc"
    executable = next((root / "dist").glob(f"*/{exe_name}"), None)
    if executable is None:
        executable = next((root / "dist").glob(f"*/ai-doc/{exe_name}"))
    subprocess.run([str(executable), "--version"], check=True, shell=False)
    subprocess.run([str(executable), "doctor", "examples/basic"], cwd=root, check=True, shell=False)
    subprocess.run([str(executable), "check", "examples/basic"], cwd=root, check=True, shell=False)
