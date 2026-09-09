from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    runtime = root / ".venv"
    if not runtime.exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", str(root)],
        check=True,
        shell=False,
    )
    print(f"ai-doc runtime ready: {runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
