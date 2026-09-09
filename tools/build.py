from __future__ import annotations

import argparse
import hashlib
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXTRA_MODULES = {
    "none": (),
    "promptfoo": ("promptfoo",),
    "deepeval": ("deepeval",),
    "deep": ("promptfoo", "deepeval"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.build")
    subcommands = parser.add_subparsers(dest="command", required=True)
    executable = subcommands.add_parser("executable", help="Build a standalone executable.")
    executable.add_argument("--mode", choices=["development", "release"], default="development")
    executable.add_argument("--onedir", action="store_true", help="Build a one-folder bundle.")
    executable.add_argument(
        "--extras",
        choices=sorted(EXTRA_MODULES),
        default="none",
        help="Optional Python integrations to include in the executable.",
    )
    args = parser.parse_args(argv)
    if args.command == "executable":
        return build_executable(mode=args.mode, onefile=not args.onedir, extras=args.extras)
    raise AssertionError(args.command)


def build_executable(mode: str = "development", onefile: bool = True, extras: str = "none") -> int:
    root = Path(__file__).resolve().parents[1]
    build = ExecutableBuild(root=root, onefile=onefile, extras=extras)
    missing = build.missing_extra_modules()
    if missing:
        print(
            "Missing optional packages for executable build: "
            + ", ".join(missing)
            + f'. Install them first, for example `python -m pip install -e ".[{extras}]"`.',
            file=sys.stderr,
        )
        return 1
    built = build.run()
    checksum_path = build.write_checksum(built)
    print(f"Built {mode} executable: {built}")
    print(f"Extras: {extras}")
    print(f"Checksum: {checksum_path}")
    return 0


@dataclass(frozen=True)
class ExecutableBuild:
    root: Path
    onefile: bool = True
    extras: str = "none"

    @property
    def dist_root(self) -> Path:
        return self.root / "dist" / platform_dir()

    @property
    def build_root(self) -> Path:
        return self.root / "build" / "pyinstaller"

    @property
    def entry(self) -> Path:
        return self.root / "tools" / "pyinstaller_entry.py"

    @property
    def executable_name(self) -> str:
        return "ai-doc.exe" if sys.platform == "win32" else "ai-doc"

    def pyinstaller_command(self) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--name",
            "ai-doc",
            "--distpath",
            str(self.dist_root),
            "--workpath",
            str(self.build_root),
            "--specpath",
            str(self.build_root),
            "--collect-data",
            "ai_doc",
            "--collect-submodules",
            "ai_doc",
        ]
        for module in self.extra_modules():
            command.extend(["--collect-submodules", module])
        if self.onefile:
            command.append("--onefile")
        command.append(str(self.entry))
        return command

    def run(self) -> Path:
        self.dist_root.mkdir(parents=True, exist_ok=True)
        subprocess.run(self.pyinstaller_command(), cwd=self.root, check=True, shell=False)
        return self.built_path()

    def built_path(self) -> Path:
        built = self.expected_built_path()
        if not built.exists() and sys.platform == "win32":
            return self.dist_root / "ai-doc.exe"
        return built

    def expected_built_path(self) -> Path:
        if self.onefile:
            return self.dist_root / self.executable_name
        return self.dist_root / "ai-doc" / self.executable_name

    def write_checksum(self, built: Path) -> Path:
        checksum_path = self.dist_root / f"{built.name}.sha256"
        checksum_path.write_text(f"{sha256(built)}  {built.name}\n", encoding="utf-8")
        return checksum_path

    def extra_modules(self) -> tuple[str, ...]:
        return extra_modules(self.extras)

    def missing_extra_modules(self) -> list[str]:
        return [module for module in self.extra_modules() if importlib.util.find_spec(module) is None]


def extra_modules(extras: str) -> tuple[str, ...]:
    try:
        return EXTRA_MODULES[extras]
    except KeyError as exc:
        raise ValueError(f"Unknown executable extras mode: {extras}") from exc


def missing_extra_modules(extras: str) -> list[str]:
    return ExecutableBuild(root=Path.cwd(), extras=extras).missing_extra_modules()


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
