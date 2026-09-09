from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.build")
    subcommands = parser.add_subparsers(dest="command", required=True)
    executable = subcommands.add_parser("executable", help="Build a standalone executable.")
    executable.add_argument("--mode", choices=["development", "release"], default="development")
    executable.add_argument("--onedir", action="store_true", help="Build a one-folder bundle.")
    args = parser.parse_args(argv)
    if args.command == "executable":
        return build_executable(mode=args.mode, onefile=not args.onedir)
    raise AssertionError(args.command)


def build_executable(mode: str = "development", onefile: bool = True) -> int:
    root = Path(__file__).resolve().parents[1]
    dist_root = root / "dist" / platform_dir()
    build_root = root / "build" / "pyinstaller"
    dist_root.mkdir(parents=True, exist_ok=True)
    entry = root / "tools" / "pyinstaller_entry.py"
    executable_name = "ai-doc.exe" if sys.platform == "win32" else "ai-doc"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "ai-doc",
        "--distpath",
        str(dist_root),
        "--workpath",
        str(build_root),
        "--specpath",
        str(build_root),
        "--collect-data",
        "ai_doc",
        "--collect-submodules",
        "ai_doc",
    ]
    if onefile:
        command.append("--onefile")
    command.append(str(entry))
    subprocess.run(command, cwd=root, check=True, shell=False)
    built = dist_root / executable_name if onefile else dist_root / "ai-doc" / executable_name
    if not built.exists() and sys.platform == "win32":
        built = dist_root / "ai-doc.exe"
    checksum_path = dist_root / f"{built.name}.sha256"
    checksum_path.write_text(f"{sha256(built)}  {built.name}\n", encoding="utf-8")
    print(f"Built {mode} executable: {built}")
    print(f"Checksum: {checksum_path}")
    return 0


def platform_dir() -> str:
    machine = {
        "AMD64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(__import__("platform").machine(), __import__("platform").machine().lower())
    if sys.platform.startswith("win"):
        return f"windows-{machine}"
    if sys.platform == "darwin":
        return f"macos-{machine}"
    return f"linux-{machine}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
