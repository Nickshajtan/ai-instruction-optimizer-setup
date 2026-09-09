from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from ai_doc.domain.documents import DocumentLink


def resolve_links(
    root: Path, document_path: Path, links: tuple[DocumentLink, ...]
) -> tuple[DocumentLink, ...]:
    resolved: list[DocumentLink] = []
    for link in links:
        parsed = urlparse(link.target)
        if parsed.scheme or parsed.netloc or link.target.startswith("#"):
            resolved.append(link)
            continue
        target_path = unquote(parsed.path)
        if not target_path.lower().endswith(".md"):
            resolved.append(link)
            continue
        absolute = (document_path.parent / target_path).resolve()
        try:
            relative = absolute.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = None
        resolved.append(
            link.model_copy(
                update={
                    "resolved_path": relative,
                    "anchor": parsed.fragment or None,
                    "is_local_markdown": True,
                    "exists": absolute.exists() if relative is not None else False,
                }
            )
        )
    return tuple(resolved)
