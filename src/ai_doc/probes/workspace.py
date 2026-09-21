from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ai_doc.domain.probes import WorkspaceDelta

IGNORED_NAMES = {".git", ".ai-doc-output", "__pycache__"}


class UnsafeWorkspaceError(RuntimeError):
    pass


def workspace_manifest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UnsafeWorkspaceError(f"Execution workspace contains unsupported symlink: {path}")
        if not path.is_file() or any(part in IGNORED_NAMES for part in path.relative_to(root).parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[path.relative_to(root).as_posix()] = digest
    return result


def assert_no_workspace_symlinks(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UnsafeWorkspaceError(
                f"Execution workspace isolation rejects unsupported symlink before copy: {path}"
            )


def compare_manifests(before: dict[str, str], after: dict[str, str]) -> WorkspaceDelta:
    before_paths = set(before)
    after_paths = set(after)
    return WorkspaceDelta(
        created_paths=sorted(after_paths - before_paths),
        modified_paths=sorted(path for path in before_paths & after_paths if before[path] != after[path]),
        deleted_paths=sorted(before_paths - after_paths),
    )


@contextmanager
def isolated_workspace(source_root: Path) -> Iterator[Path]:
    assert_no_workspace_symlinks(source_root)
    workspace_manifest(source_root)
    with tempfile.TemporaryDirectory(prefix="ai-doc-exec-") as temporary:
        destination = Path(temporary) / "repo"
        shutil.copytree(
            source_root,
            destination,
            symlinks=True,
            ignore=shutil.ignore_patterns(*IGNORED_NAMES),
        )
        assert_no_workspace_symlinks(destination)
        yield destination
