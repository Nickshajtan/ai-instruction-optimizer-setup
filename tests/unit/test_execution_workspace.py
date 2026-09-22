from pathlib import Path

import pytest

from ai_doc.probes.workspace import UnsafeWorkspaceError, compare_manifests, isolated_workspace, workspace_manifest


def test_workspace_manifest_and_delta(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("before", encoding="utf-8")
    (tmp_path / "delete.txt").write_text("gone", encoding="utf-8")
    before = workspace_manifest(tmp_path)

    (tmp_path / "keep.txt").write_text("after", encoding="utf-8")
    (tmp_path / "delete.txt").unlink()
    (tmp_path / "created.txt").write_text("new", encoding="utf-8")
    after = workspace_manifest(tmp_path)

    delta = compare_manifests(before, after)
    assert delta.created_paths == ["created.txt"]
    assert delta.modified_paths == ["keep.txt"]
    assert delta.deleted_paths == ["delete.txt"]


def test_workspace_manifest_rejects_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")

    with pytest.raises(UnsafeWorkspaceError):
        workspace_manifest(tmp_path)


def test_isolated_workspace_copies_ordinary_repository(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")

    with isolated_workspace(tmp_path) as workspace:
        assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "# Rules\n"


def test_isolated_workspace_rejects_file_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    _make_symlink(link, target)

    with pytest.raises(UnsafeWorkspaceError, match="isolation rejects unsupported symlink"), isolated_workspace(
        tmp_path
    ):
        pass


def test_isolated_workspace_rejects_directory_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target-dir"
    target.mkdir()
    link = tmp_path / "link-dir"
    _make_symlink(link, target, target_is_directory=True)

    with pytest.raises(UnsafeWorkspaceError, match="isolation rejects unsupported symlink"), isolated_workspace(
        tmp_path
    ):
        pass


def test_isolated_workspace_rejects_symlink_to_outside_repository(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "outside-link.txt"
    _make_symlink(link, outside)

    with pytest.raises(UnsafeWorkspaceError, match="isolation rejects unsupported symlink"), isolated_workspace(
        tmp_path
    ):
        pass


def _make_symlink(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
