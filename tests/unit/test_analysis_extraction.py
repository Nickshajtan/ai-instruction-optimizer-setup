from pathlib import Path

from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.analysis import NormalizationPolicy, Polarity, TextUnitKind
from ai_doc.markdown.extraction import DeterministicInstructionExtractor, extract_text_units, normalize_text
from ai_doc.tokens.counter import ApproximateTokenCounter


def _document(tmp_path: Path, text: str):  # type: ignore[no-untyped-def]
    (tmp_path / "AGENTS.md").write_text(text, encoding="utf-8")
    return discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter()).documents[0]


def test_extracts_markdown_structure_without_treating_code_as_prose(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "# Rules\n\nParagraph with `v1.2` and [docs](guide.md).\n\n"
        "- **Always** validate `generated.py`.\n  Continue on the next line.\n\n"
        "```text\nNever validate generated.py.\n```\n",
    )
    units = extract_text_units(document)
    assert [unit.kind for unit in units] == [
        TextUnitKind.HEADING,
        TextUnitKind.PARAGRAPH,
        TextUnitKind.LIST_ITEM,
        TextUnitKind.CODE_BLOCK,
    ]
    assert "Continue on the next line." in units[2].text
    assert units[2].section == "Rules"


def test_instruction_extractor_handles_formatting_and_ignores_fenced_code(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "# Rules\n\n- **Always** validate changes.\n- Never validate changes.\n\n"
        "```text\nNever deploy changes.\n```\n",
    )
    instructions = DeterministicInstructionExtractor().extract(document)
    assert [(item.polarity, item.proposition) for item in instructions] == [
        (Polarity.POSITIVE, "validate changes"),
        (Polarity.NEGATIVE, "validate changes"),
    ]


def test_normalization_policies_are_explicit() -> None:
    assert normalize_text("Use `foo.py` here", NormalizationPolicy.DUPLICATION) == "use `code` here"
    assert normalize_text("**Validate** changes!", NormalizationPolicy.LITERAL_PROPOSITION) == "validate changes"
