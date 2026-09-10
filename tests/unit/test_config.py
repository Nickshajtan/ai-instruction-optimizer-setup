from pathlib import Path

import pytest

from ai_doc.config.loader import ConfigError, ConfigFileReader, ProjectConfigLoadStrategy, load_config
from ai_doc.config.models import DEFAULT_CONFIG, AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_config_rejects_unknown_keys(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\nunknown: true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_default_excludes_skip_source_checkout_tool_docs(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Target instructions\n", encoding="utf-8")
    tool_docs = tmp_path / ".tools" / "ai-doc" / "docs"
    tool_docs.mkdir(parents=True)
    (tool_docs / "getting-started.md").write_text("# Tool docs\n", encoding="utf-8")

    config = DEFAULT_CONFIG.model_copy(deep=True)
    config.include = ["**/*.md"]
    snapshot = discover_markdown(tmp_path, config, ApproximateTokenCounter())

    assert [document.relative_path for document in snapshot.documents] == ["AGENTS.md"]


def test_load_config_merges_nested_module_config_with_scoped_patterns(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include:
  - AGENTS.md
  - "modules/*/README.md"
profiles:
  AGENTS.md: instruction
  "modules/**": reference
exclude:
  - .tools/ai-doc/**
""",
        encoding="utf-8",
    )
    module = tmp_path / "modules" / "payments"
    module.mkdir(parents=True)
    (module / ".ai-doc.yaml").write_text(
        """
version: 1
include:
  - AGENTS.md
  - "docs/**/*.md"
exclude:
  - "docs/private/**"
profiles:
  AGENTS.md: instruction
  "docs/**": reference
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert "modules/payments/AGENTS.md" in config.include
    assert "modules/payments/docs/**/*.md" in config.include
    assert "modules/payments/docs/private/**" in config.exclude
    assert config.profiles["modules/payments/AGENTS.md"] is DocumentProfile.INSTRUCTION
    assert config.profiles["modules/payments/docs/**"] is DocumentProfile.REFERENCE


def test_nested_config_contributes_to_discovery_and_profiles(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text(
        """
version: 1
include:
  - AGENTS.md
  - "modules/*/README.md"
profiles:
  AGENTS.md: instruction
  "modules/**": reference
exclude: []
""",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("# Root\n", encoding="utf-8")
    module = tmp_path / "modules" / "payments"
    private = module / "docs" / "private"
    private.mkdir(parents=True)
    (module / ".ai-doc.yaml").write_text(
        """
version: 1
include:
  - AGENTS.md
  - "docs/**/*.md"
exclude:
  - "docs/private/**"
profiles:
  AGENTS.md: instruction
  "docs/**": reference
""",
        encoding="utf-8",
    )
    (module / "README.md").write_text("# Payments\n", encoding="utf-8")
    (module / "AGENTS.md").write_text("# Payments rules\n", encoding="utf-8")
    (module / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (private / "secret.md").write_text("# Secret\n", encoding="utf-8")

    config = load_config(tmp_path)
    snapshot = discover_markdown(tmp_path, config, ApproximateTokenCounter())

    profiles = {document.relative_path: document.profile for document in snapshot.documents}
    assert profiles == {
        "AGENTS.md": DocumentProfile.INSTRUCTION,
        "modules/payments/AGENTS.md": DocumentProfile.INSTRUCTION,
        "modules/payments/README.md": DocumentProfile.REFERENCE,
        "modules/payments/docs/guide.md": DocumentProfile.REFERENCE,
    }


def test_explicit_config_does_not_merge_nested_configs(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("version: 1\ninclude: [AGENTS.md]\n", encoding="utf-8")
    module = tmp_path / "module"
    module.mkdir()
    (module / ".ai-doc.yaml").write_text("version: 1\ninclude: [AGENTS.md]\n", encoding="utf-8")

    config = load_config(tmp_path, explicit)

    assert config.include == ["AGENTS.md"]


def test_nested_config_rejects_paths_outside_nested_directory(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\ninclude: []\n", encoding="utf-8")
    module = tmp_path / "module"
    module.mkdir()
    (module / ".ai-doc.yaml").write_text(
        'version: 1\ninclude: ["../outside.md"]\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="inside its own directory"):
        load_config(tmp_path)


def test_missing_root_config_does_not_merge_nested_configs(tmp_path: Path) -> None:
    module = tmp_path / "module"
    module.mkdir()
    (module / ".ai-doc.yaml").write_text("version: 1\ninclude: [AGENTS.md]\n", encoding="utf-8")

    config = load_config(tmp_path)

    assert "module/AGENTS.md" not in config.include


class RecordingNestedMerge:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, AiDocConfig]] = []

    def merge(self, root: Path, config: AiDocConfig) -> AiDocConfig:
        self.calls.append((root, config))
        merged = config.model_copy(deep=True)
        merged.include.append("merged.md")
        return merged


def test_project_config_strategy_uses_injected_nested_merge(tmp_path: Path) -> None:
    (tmp_path / ".ai-doc.yaml").write_text("version: 1\ninclude: [AGENTS.md]\n", encoding="utf-8")
    nested_merge = RecordingNestedMerge()

    config = ProjectConfigLoadStrategy(
        tmp_path,
        reader=ConfigFileReader(),
        nested_merge=nested_merge,
    ).load()

    assert config.include == ["AGENTS.md", "merged.md"]
    assert nested_merge.calls[0][0] == tmp_path.resolve()
