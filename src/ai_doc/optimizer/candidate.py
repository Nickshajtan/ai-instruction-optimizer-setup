from __future__ import annotations

import difflib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.proposals import CandidateProposal


def create_run_dir(output_root: Path) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / run_id
    suffix = 1
    while run_dir.exists():
        suffix += 1
        run_dir = output_root / f"{run_id}-{suffix}"
    run_dir.mkdir(parents=True)
    return run_dir


def write_candidate_tree(
    snapshot: DocumentationSnapshot, rendered: dict[str, str], run_dir: Path
) -> Path:
    candidate_dir = run_dir / "candidate"
    for document in snapshot.documents:
        destination = candidate_dir / document.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            rendered.get(document.relative_path, document.text), encoding="utf-8"
        )
    for relative, text in rendered.items():
        destination = candidate_dir / relative
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return candidate_dir


def write_snapshot_tree(snapshot: DocumentationSnapshot, destination: Path) -> Path:
    for document in snapshot.documents:
        target = destination / document.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document.text, encoding="utf-8")
    return destination


def write_proposal(proposal: CandidateProposal, run_dir: Path) -> Path:
    path = run_dir / "proposal.json"
    path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_diff(snapshot: DocumentationSnapshot, rendered: dict[str, str], run_dir: Path) -> Path:
    diff_path = run_dir / "diff.patch"
    chunks: list[str] = []
    baseline_paths = {document.relative_path for document in snapshot.documents}
    for document in snapshot.documents:
        new_text = rendered.get(document.relative_path, document.text)
        chunks.extend(
            difflib.unified_diff(
                document.text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{document.relative_path}",
                tofile=f"b/{document.relative_path}",
            )
        )
    for relative, text in rendered.items():
        if relative in baseline_paths:
            continue
        chunks.extend(
            difflib.unified_diff(
                [],
                text.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile=f"b/{relative}",
            )
        )
    diff_path.write_text("".join(chunks), encoding="utf-8")
    return diff_path


def copy_untracked_context(root: Path, candidate_dir: Path, include: list[str]) -> None:
    del include
    for name in [".ai-doc.yaml", ".ai-doc"]:
        source = root / name
        destination = candidate_dir / name
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        elif source.is_dir() and not destination.exists():
            shutil.copytree(source, destination)


def write_report_json(data: dict[str, object], run_dir: Path) -> Path:
    path = run_dir / "report.json"
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path
