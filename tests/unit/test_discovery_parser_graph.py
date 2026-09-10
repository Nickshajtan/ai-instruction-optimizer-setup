from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.markdown.links import resolve_links
from ai_doc.markdown.parser import MarkdownParser
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_discovery_parser_and_graph(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Root\n\nSee [details](docs/details.md).\n", encoding="utf-8"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "details.md").write_text("# Details\n\nContent.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    assert [doc.relative_path for doc in snapshot.documents] == ["AGENTS.md", "docs/details.md"]
    assert snapshot.documents[0].headings[0].title == "Root"
    graph = DocumentGraph(snapshot)
    assert graph.outgoing("AGENTS.md") == ["docs/details.md"]
    assert graph.incoming("docs/details.md") == ["AGENTS.md"]


def test_parser_assigns_unique_duplicate_heading_slugs() -> None:
    parsed = MarkdownParser(ApproximateTokenCounter()).parse(
        "# Intro\n\n## Intro\n\n## Intro!\n"
    )

    assert [heading.slug for heading in parsed.headings] == ["intro", "intro-1", "intro-2"]


def test_parser_extracts_link_labels_from_inline_tokens() -> None:
    parsed = MarkdownParser(ApproximateTokenCounter()).parse(
        "See [**detailed** setup](docs/setup.md) and [`API`](docs/api.md).\n"
    )

    assert [(link.label, link.target) for link in parsed.links] == [
        ("detailed setup", "docs/setup.md"),
        ("API", "docs/api.md"),
    ]


def test_resolve_links_handles_local_markdown_edge_cases(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = tmp_path / "AGENTS.md"
    source.write_text(
        "\n".join(
            [
                "# Root",
                "",
                "[encoded](docs/My%20File.md#Install)",
                "[missing](docs/missing.md)",
                "[asset](docs/image.png)",
                "[external](https://example.com/docs.md)",
                "[anchor](#local)",
            ]
        ),
        encoding="utf-8",
    )
    (docs / "My File.md").write_text("# Install\n", encoding="utf-8")
    parsed = MarkdownParser(ApproximateTokenCounter()).parse(source.read_text(encoding="utf-8"))

    resolved = resolve_links(tmp_path, source, parsed.links)

    assert resolved[0].is_local_markdown is True
    assert resolved[0].resolved_path == "docs/My File.md"
    assert resolved[0].anchor == "Install"
    assert resolved[0].exists is True
    assert resolved[1].is_local_markdown is True
    assert resolved[1].resolved_path == "docs/missing.md"
    assert resolved[1].exists is False
    assert resolved[2].is_local_markdown is False
    assert resolved[3].is_local_markdown is False
    assert resolved[4].is_local_markdown is False


def test_resolve_links_marks_root_escape_as_unresolved_local_markdown(tmp_path: Path) -> None:
    source = tmp_path / "AGENTS.md"
    source.write_text("[outside](../outside.md)\n", encoding="utf-8")
    parsed = MarkdownParser(ApproximateTokenCounter()).parse(source.read_text(encoding="utf-8"))

    resolved = resolve_links(tmp_path, source, parsed.links)

    assert resolved[0].is_local_markdown is True
    assert resolved[0].resolved_path is None
    assert resolved[0].exists is False
