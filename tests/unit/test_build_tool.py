import os
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


def test_pyinstaller_command_collects_local_ml_runtime() -> None:
    build = ExecutableBuild(
        root=Path("repo"),
        onefile=True,
        extras="ml",
    )
    command = build.pyinstaller_command()

    assert command.count("--collect-submodules") == 4
    assert "ai_doc" in command
    assert "sentence_transformers" in command
    assert "transformers" in command
    assert "torch" in command
    assert "--onefile" in command


def test_pyinstaller_command_can_bundle_local_model_weights(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    (model_root / "similarity").mkdir(parents=True)
    (model_root / "nli").mkdir()
    build = ExecutableBuild(root=Path("repo"), extras="ml", model_root=model_root)

    command = build.pyinstaller_command()
    add_data = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--add-data"]

    assert f"{model_root / 'similarity'}{os.pathsep}ai_doc_models/similarity" in add_data
    assert f"{model_root / 'nli'}{os.pathsep}ai_doc_models/nli" in add_data
    assert build.model_bundle_error() is None


def test_model_bundle_requires_ml_runtime(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    (model_root / "similarity").mkdir(parents=True)
    (model_root / "nli").mkdir()

    build = ExecutableBuild(root=Path("repo"), extras="none", model_root=model_root)

    assert build.model_bundle_error() == "--model-root requires --extras ml so the local ML runtime is bundled too."


def test_model_bundle_requires_both_model_slots(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    (model_root / "similarity").mkdir(parents=True)

    build = ExecutableBuild(root=Path("repo"), extras="ml", model_root=model_root)

    assert build.model_bundle_error() == "Model root must contain directories: nli/"


def test_extra_modules_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        extra_modules("everything")


def test_missing_extra_modules_reports_missing_packages(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.build.importlib.util.find_spec",
        lambda module: object() if module == "promptfoo" else None,
    )

    assert missing_extra_modules("deep") == ["deepeval"]


def test_missing_ml_runtime_reports_transitive_packages(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.build.importlib.util.find_spec",
        lambda module: object() if module == "sentence_transformers" else None,
    )

    assert missing_extra_modules("ml") == ["transformers", "torch"]


def test_executable_build_paths_for_onedir() -> None:
    build = ExecutableBuild(root=Path("repo"), onefile=False)

    assert build.dist_root.parent == Path("repo") / "dist"
    assert build.build_root == Path("repo") / "build" / "pyinstaller"
    assert build.entry == Path("repo") / "tools" / "pyinstaller_entry.py"
    assert build.expected_built_path().parent.name == "ai-doc"
