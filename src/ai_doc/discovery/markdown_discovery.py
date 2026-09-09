from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from ai_doc.config.models import AiDocConfig
from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.markdown.links import resolve_links
from ai_doc.markdown.parser import MarkdownParser
from ai_doc.tokens.counter import TokenCounter


def discover_markdown(
    root: Path, config: AiDocConfig, token_counter: TokenCounter
) -> DocumentationSnapshot:
    root = root.resolve()
    parser = MarkdownParser(token_counter)
    paths: set[Path] = set()
    for pattern in config.include:
        for path in root.glob(pattern):
            if (
                path.is_file()
                and path.suffix.lower() == ".md"
                and not _is_excluded(root, path, config.exclude)
            ):
                paths.add(path.resolve())
    documents: list[Document] = []
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        text = path.read_text(encoding="utf-8")
        parsed = parser.parse(text)
        relative = path.relative_to(root).as_posix()
        links = resolve_links(root, path, parsed.links)
        documents.append(
            Document(
                path=path,
                relative_path=relative,
                profile=_profile_for(relative, config),
                text=text,
                token_count=token_counter.count(text),
                headings=parsed.headings,
                sections=parsed.sections,
                links=links,
            )
        )
    return DocumentationSnapshot(root=root, documents=tuple(documents))


def _is_excluded(root: Path, path: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(fnmatch(relative, pattern) for pattern in patterns)


def _profile_for(relative: str, config: AiDocConfig) -> DocumentProfile:
    for pattern, profile in config.profiles.items():
        if fnmatch(relative, pattern):
            return profile
    return DocumentProfile.GENERIC
