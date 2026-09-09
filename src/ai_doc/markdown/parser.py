from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

from ai_doc.domain.documents import DocumentLink, Heading, Section
from ai_doc.tokens.counter import TokenCounter


@dataclass(frozen=True)
class ParsedMarkdown:
    headings: tuple[Heading, ...]
    sections: tuple[Section, ...]
    links: tuple[DocumentLink, ...]


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower(), flags=re.UNICODE)
    return re.sub(r"[\s_-]+", "-", slug).strip("-")


class MarkdownParser:
    def __init__(self, token_counter: TokenCounter) -> None:
        self._md = MarkdownIt("commonmark")
        self._token_counter = token_counter

    def parse(self, text: str) -> ParsedMarkdown:
        tokens = self._md.parse(text)
        lines = text.splitlines()
        headings: list[Heading] = []
        links: list[DocumentLink] = []
        slug_counts: Counter[str] = Counter()
        for idx, token in enumerate(tokens):
            if token.type == "heading_open" and token.map:
                inline = tokens[idx + 1] if idx + 1 < len(tokens) else None
                title = inline.content.strip() if inline and inline.type == "inline" else ""
                slug = _unique_slug(slugify(title), slug_counts)
                headings.append(
                    Heading(
                        level=int(token.tag[1:]),
                        title=title,
                        line=token.map[0] + 1,
                        slug=slug,
                    )
                )
            if token.type == "inline" and token.children:
                for child_index, child in enumerate(token.children):
                    if child.type == "link_open":
                        href = str(child.attrs.get("href", "") if child.attrs else "")
                        links.append(
                            DocumentLink(
                                label=_link_label(token.children, child_index, href),
                                target=href,
                                line=(token.map[0] + 1) if token.map else 1,
                            )
                        )
        return ParsedMarkdown(
            headings=tuple(headings),
            sections=tuple(_sections(lines, headings, self._token_counter)),
            links=tuple(links),
        )


def _sections(
    lines: list[str], headings: list[Heading], token_counter: TokenCounter
) -> list[Section]:
    if not headings:
        text = "\n".join(lines)
        return [
            Section(
                heading=None,
                text=text,
                token_count=token_counter.count(text),
                start_line=1,
                end_line=len(lines),
            )
        ]
    sections: list[Section] = []
    for index, heading in enumerate(headings):
        start = heading.line
        end = headings[index + 1].line - 1 if index + 1 < len(headings) else len(lines)
        section_text = "\n".join(lines[start - 1 : end])
        sections.append(
            Section(
                heading=heading,
                text=section_text,
                token_count=token_counter.count(section_text),
                start_line=start,
                end_line=end,
            )
        )
    return sections


def _unique_slug(slug: str, slug_counts: Counter[str]) -> str:
    count = slug_counts[slug]
    slug_counts[slug] += 1
    return slug if count == 0 else f"{slug}-{count}"


def _link_label(children: list[Token], open_index: int, href: str) -> str:
    parts: list[str] = []
    depth = 0
    for child in children[open_index + 1 :]:
        if child.type == "link_open":
            depth += 1
            continue
        if child.type == "link_close":
            if depth == 0:
                break
            depth -= 1
            continue
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        if child.type == "softbreak":
            parts.append(" ")
    label = "".join(parts).strip()
    return label or href
