from pathlib import Path

import pytest

from tools.build import ExecutableBuild, extra_modules, missing_extra_modules


def test_pyinstaller_command_collects_deep_extra_modules() -> None:
    build = ExecutableBuild(
        root=Path("repo"),
        onefile=True,
        extras="deep",
    )
    command = build.pyinstaller_command()

    assert command.count("--collect-submodules") == 3
    assert "ai_doc" in command
    assert "promptfoo" in command
    assert "deepeval" in command
    assert "--onefile" in command


def test_extra_modules_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        extra_modules("everything")


def test_missing_extra_modules_reports_missing_packages(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.build.importlib.util.find_spec",
        lambda module: object() if module == "promptfoo" else None,
    )

    assert missing_extra_modules("deep") == ["deepeval"]


def test_executable_build_paths_for_onedir() -> None:
    build = ExecutableBuild(root=Path("repo"), onefile=False)

    assert build.dist_root.parent == Path("repo") / "dist"
    assert build.build_root == Path("repo") / "build" / "pyinstaller"
    assert build.entry == Path("repo") / "tools" / "pyinstaller_entry.py"
    assert build.expected_built_path().parent.name == "ai-doc"
