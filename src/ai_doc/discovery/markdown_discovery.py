from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path

from ai_doc.config.models import AiDocConfig
from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.markdown.links import resolve_links
from ai_doc.markdown.parser import MarkdownParser, ParsedMarkdown
from ai_doc.tokens.counter import TokenCounter

MARKDOWN_LIKE_SUFFIXES = {".md", ".mdc"}


def discover_markdown(root: Path, config: AiDocConfig, token_counter: TokenCounter) -> DocumentationSnapshot:
    root = root.resolve()
    parser = MarkdownParser(token_counter)
    paths: set[Path] = set()
    for pattern in config.include:
        for path in root.glob(pattern):
            if (
                path.is_file()
                and path.suffix.lower() in MARKDOWN_LIKE_SUFFIXES
                and not _is_excluded(root, path, config.exclude)
            ):
                paths.add(path.resolve())
    parsed_documents: list[tuple[Path, str, ParsedMarkdown]] = []
    sorted_paths = sorted(paths, key=lambda item: item.relative_to(root).as_posix())
    texts: list[str] = []
    for path in sorted_paths:
        text = path.read_text(encoding="utf-8")
        parsed = parser.parse(text)
        parsed_documents.append((path, text, parsed))
        texts.append(text)
    document_token_counts = _count_many(token_counter, texts)

    documents: list[Document] = []
    for (path, text, parsed), token_count in zip(parsed_documents, document_token_counts, strict=True):
        relative = path.relative_to(root).as_posix()
        links = resolve_links(root, path, parsed.links)
        documents.append(
            Document(
                path=path,
                relative_path=relative,
                profile=_profile_for(relative, config),
                text=text,
                token_count=token_count,
                headings=parsed.headings,
                sections=parsed.sections,
                links=links,
            )
        )
    return DocumentationSnapshot(root=root, documents=tuple(documents))


def _count_many(token_counter: TokenCounter, texts: list[str]) -> list[int]:
    count_many = getattr(token_counter, "count_many", None)
    if callable(count_many):
        result = count_many(texts)
        if isinstance(result, list) and len(result) == len(texts):
            return result
    return [token_counter.count(text) for text in texts]


def _is_excluded(root: Path, path: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(fnmatch(relative, pattern) for pattern in patterns)


def _profile_for(relative: str, config: AiDocConfig) -> DocumentProfile:
    for pattern, profile in config.profiles.items():
        if _matches_pattern(relative, pattern):
            return profile
    return DocumentProfile.GENERIC


def _matches_pattern(relative: str, pattern: str) -> bool:
    if fnmatch(relative, pattern):
        return True
    if "/**/" in pattern:
        return fnmatch(relative, pattern.replace("/**/", "/"))
    return False
