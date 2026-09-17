from pathlib import Path

import pytest

from ai_doc.composition import register_configured_extensions, resolve_configured_evaluator
from ai_doc.config.loader import (
    ConfigError,
    ConfigFileReader,
    ExplicitConfigLoadStrategy,
    ProjectConfigLoadStrategy,
    load_config,
    write_default_config,
)
from ai_doc.config.models import DEFAULT_CONFIG, AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.extensions.process import ProcessEvaluator
from ai_doc.extensions.transport import ProcessTransport
from ai_doc.plugins.registry import ExtensionRegistry
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


def test_default_agent_ecosystem_discovery_and_profiles(tmp_path: Path) -> None:
    files = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".github/copilot-instructions.md",
        ".github/instructions/backend.instructions.md",
        ".codex/skills/review/SKILL.md",
        ".claude/skills/review/SKILL.md",
        ".gemini/skills/review/SKILL.md",
        ".agents/skills/shared-review/SKILL.md",
        ".cursor/rules/backend.mdc",
    ]
    for relative in files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\napplyTo: '**/*.py'\n---\n# Rules\n\nUse project conventions.\n", encoding="utf-8")

    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())

    profiles = {document.relative_path: document.profile for document in snapshot.documents}
    assert profiles == {
        "AGENTS.md": DocumentProfile.INSTRUCTION,
        "CLAUDE.md": DocumentProfile.INSTRUCTION,
        "GEMINI.md": DocumentProfile.INSTRUCTION,
        ".github/copilot-instructions.md": DocumentProfile.INSTRUCTION,
        ".github/instructions/backend.instructions.md": DocumentProfile.INSTRUCTION,
        ".codex/skills/review/SKILL.md": DocumentProfile.SKILL,
        ".claude/skills/review/SKILL.md": DocumentProfile.SKILL,
        ".gemini/skills/review/SKILL.md": DocumentProfile.SKILL,
        ".agents/skills/shared-review/SKILL.md": DocumentProfile.SKILL,
        ".cursor/rules/backend.mdc": DocumentProfile.INSTRUCTION,
    }
    cursor_rule = snapshot.by_relative_path()[".cursor/rules/backend.mdc"]
    assert cursor_rule.text.startswith("---\napplyTo")


def test_markdown_like_mdc_links_resolve(tmp_path: Path) -> None:
    rules = tmp_path / ".cursor" / "rules"
    rules.mkdir(parents=True)
    (rules / "backend.mdc").write_text("# Backend\n\nSee [frontend](frontend.mdc).\n", encoding="utf-8")
    (rules / "frontend.mdc").write_text("# Frontend\n", encoding="utf-8")

    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())

    backend = snapshot.by_relative_path()[".cursor/rules/backend.mdc"]
    assert backend.links[0].is_local_markdown is True
    assert backend.links[0].resolved_path == ".cursor/rules/frontend.mdc"


def test_default_config_resource_matches_agent_discovery_defaults(tmp_path: Path) -> None:
    written = write_default_config(tmp_path)

    assert tmp_path / ".ai-doc.yaml" in written
    config = load_config(tmp_path)
    for pattern in [
        "GEMINI.md",
        ".gemini/**/*.md",
        ".agents/skills/**/SKILL.md",
        ".github/copilot-instructions.md",
        ".github/instructions/**/*.instructions.md",
        ".cursor/rules/**/*.mdc",
    ]:
        assert pattern in config.include
    assert config.profiles["GEMINI.md"] is DocumentProfile.INSTRUCTION
    assert config.profiles[".gemini/skills/**/SKILL.md"] is DocumentProfile.SKILL
    assert config.profiles[".agents/skills/**/SKILL.md"] is DocumentProfile.SKILL
    assert config.profiles[".github/copilot-instructions.md"] is DocumentProfile.INSTRUCTION
    assert config.profiles[".github/instructions/**/*.instructions.md"] is DocumentProfile.INSTRUCTION
    assert config.profiles[".cursor/rules/**/*.mdc"] is DocumentProfile.INSTRUCTION


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


def test_explicit_missing_config_path_fails(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    with pytest.raises(ConfigError, match="Explicit ai-doc configuration does not exist"):
        load_config(tmp_path, missing)


def test_implicit_missing_project_config_still_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)

    assert config == DEFAULT_CONFIG


def test_explicit_config_strategy_checks_existence_before_reader(tmp_path: Path) -> None:
    class DefaultingReader:
        def load(self, _path: Path) -> AiDocConfig:
            return DEFAULT_CONFIG.model_copy(deep=True)

    with pytest.raises(ConfigError):
        ExplicitConfigLoadStrategy(tmp_path / "missing.yaml", reader=DefaultingReader()).load()  # type: ignore[arg-type]


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


def test_command_evaluator_config_registers_at_composition_boundary() -> None:
    config = AiDocConfig.model_validate(
        {
            "evaluation": {"deep": {"evaluator": "instruction-quality"}},
            "extension_runtime": {
                "evaluators": {
                    "instruction-quality": {
                        "type": "command",
                        "command": ["external-quality-evaluator"],
                        "timeout": 30,
                    }
                }
            },
        }
    )
    registry = register_configured_extensions(config, ExtensionRegistry())

    evaluator = resolve_configured_evaluator(config, registry, "deep")

    assert isinstance(evaluator, ProcessEvaluator)
    assert isinstance(evaluator.transport, ProcessTransport)
    assert evaluator.transport.command == ("external-quality-evaluator",)
