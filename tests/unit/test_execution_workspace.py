from pathlib import Path

import pytest

from ai_doc.probes.workspace import UnsafeWorkspaceError, compare_manifests, workspace_manifest


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
