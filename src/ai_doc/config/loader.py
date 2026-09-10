from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import ValidationError

from ai_doc.config.models import DEFAULT_CONFIG, AiDocConfig, ExtensionConfig
from ai_doc.domain.documents import DocumentProfile
from ai_doc.resource_loader import read_text_resource


class ConfigError(ValueError):
    pass


class ConfigLoadStrategy(Protocol):
    def load(self) -> AiDocConfig:
        ...


class ConfigFileReader:
    def load(self, path: Path) -> AiDocConfig:
        if not path.exists():
            return DEFAULT_CONFIG.model_copy(deep=True)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
        try:
            return AiDocConfig.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"Invalid ai-doc configuration in {path}:\n{exc}") from exc


class ExplicitConfigLoadStrategy:
    def __init__(self, config_path: Path, reader: ConfigFileReader | None = None) -> None:
        self.config_path = config_path
        self.reader = reader or ConfigFileReader()

    def load(self) -> AiDocConfig:
        return self.reader.load(self.config_path)


@dataclass
class NestedConfigMergeContext:
    root: Path
    merged: AiDocConfig
    nested_profiles: dict[str, DocumentProfile] = field(default_factory=dict)


class NestedConfigMergeRule(Protocol):
    field_name: str

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        ...


class IncludeMergeRule:
    field_name = "include"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        context.merged.include.extend(_prefix_patterns(relative_dir, nested.include, path))


class ExcludeMergeRule:
    field_name = "exclude"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        context.merged.exclude.extend(_prefix_patterns(relative_dir, nested.exclude, path))


class ProfilesMergeRule:
    field_name = "profiles"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        context.nested_profiles.update(
            {
                _prefix_pattern(relative_dir, pattern, path): profile
                for pattern, profile in nested.profiles.items()
            }
        )


class LoadingMergeRule:
    field_name = "loading"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        context.merged.loading.update(
            {
                _prefix_pattern(relative_dir, pattern, path): loading
                for pattern, loading in nested.loading.items()
            }
        )


class ExtensionsMergeRule:
    field_name = "extensions"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, relative_dir: str, path: Path) -> None:
        context.merged.extensions.extend(
            ExtensionConfig(path=_prefix_pattern(relative_dir, extension.path, path))
            for extension in nested.extensions
        )


class DictUpdateMergeRule:
    def __init__(self, field_name: str) -> None:
        self.field_name = field_name

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, _relative_dir: str, _path: Path) -> None:
        getattr(context.merged, self.field_name).update(getattr(nested, self.field_name))


class OptimizationMergeRule:
    field_name = "optimization"

    def merge(self, context: NestedConfigMergeContext, nested: AiDocConfig, _relative_dir: str, _path: Path) -> None:
        context.merged.optimization = nested.optimization


DEFAULT_NESTED_MERGE_RULES: tuple[NestedConfigMergeRule, ...] = (
    IncludeMergeRule(),
    ExcludeMergeRule(),
    ProfilesMergeRule(),
    LoadingMergeRule(),
    ExtensionsMergeRule(),
    DictUpdateMergeRule("budgets"),
    DictUpdateMergeRule("pricing"),
    DictUpdateMergeRule("evaluation"),
    OptimizationMergeRule(),
)


class NestedConfigMergeStrategy:
    def __init__(
        self,
        reader: ConfigFileReader | None = None,
        rules: Iterable[NestedConfigMergeRule] = DEFAULT_NESTED_MERGE_RULES,
    ) -> None:
        self.reader = reader or ConfigFileReader()
        self.rules = tuple(rules)

    def merge(self, root: Path, config: AiDocConfig) -> AiDocConfig:
        nested_paths = [path for path in _iter_nested_config_paths(root, config.exclude)]
        if not nested_paths:
            return config

        context = NestedConfigMergeContext(root=root, merged=config.model_copy(deep=True))
        for path in nested_paths:
            relative_dir = path.parent.relative_to(root).as_posix()
            nested = self.reader.load(path)
            self._merge_nested_config(context, nested, relative_dir, path)

        context.merged.profiles = {**context.nested_profiles, **context.merged.profiles}
        return context.merged

    def _merge_nested_config(
        self,
        context: NestedConfigMergeContext,
        nested: AiDocConfig,
        relative_dir: str,
        path: Path,
    ) -> None:
        fields = nested.model_fields_set
        for rule in self.rules:
            if rule.field_name in fields:
                rule.merge(context, nested, relative_dir, path)


class ProjectConfigLoadStrategy:
    def __init__(
        self,
        root: Path,
        reader: ConfigFileReader | None = None,
        nested_merge: NestedConfigMergeStrategy | None = None,
    ) -> None:
        self.root = root
        self.path = root / ".ai-doc.yaml"
        self.reader = reader or ConfigFileReader()
        self.nested_merge = nested_merge or NestedConfigMergeStrategy(self.reader)

    def load(self) -> AiDocConfig:
        if not self.path.exists():
            return DEFAULT_CONFIG.model_copy(deep=True)
        config = self.reader.load(self.path)
        return self.nested_merge.merge(self.root.resolve(), config)


class ConfigLoader:
    def __init__(self, strategy: ConfigLoadStrategy) -> None:
        self.strategy = strategy

    def load(self) -> AiDocConfig:
        return self.strategy.load()


def load_config(root: Path, config_path: Path | None = None) -> AiDocConfig:
    strategy: ConfigLoadStrategy = (
        ExplicitConfigLoadStrategy(config_path)
        if config_path is not None
        else ProjectConfigLoadStrategy(root)
    )
    return ConfigLoader(strategy).load()


def _load_one_config(path: Path) -> AiDocConfig:
    return ConfigFileReader().load(path)


def _merge_nested_configs(root: Path, config: AiDocConfig) -> AiDocConfig:
    return NestedConfigMergeStrategy().merge(root, config)


def _iter_nested_config_paths(root: Path, exclude: list[str]) -> list[Path]:
    paths: list[Path] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        relative_current = current_path.relative_to(root).as_posix()
        dirs[:] = [
            directory
            for directory in dirs
            if not _should_prune_directory(relative_current, directory, exclude)
        ]
        if ".ai-doc.yaml" not in files:
            continue
        config_path = current_path / ".ai-doc.yaml"
        if config_path == root / ".ai-doc.yaml":
            continue
        relative_config = config_path.relative_to(root).as_posix()
        if _matches_any(relative_config, exclude):
            continue
        paths.append(config_path)
    return sorted(paths, key=lambda item: (-len(item.relative_to(root).parts), item.as_posix()))


def _should_prune_directory(relative_parent: str, directory: str, exclude: list[str]) -> bool:
    if directory in {".git", ".venv", "__pycache__"}:
        return True
    relative = directory if relative_parent == "." else f"{relative_parent}/{directory}"
    return _matches_any(f"{relative}/__probe__", exclude)


def _prefix_patterns(relative_dir: str, patterns: list[str], config_path: Path) -> list[str]:
    return [_prefix_pattern(relative_dir, pattern, config_path) for pattern in patterns]


def _prefix_pattern(relative_dir: str, pattern: str, config_path: Path) -> str:
    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(
            f"Nested ai-doc configuration in {config_path} must use paths inside its own directory: {pattern}"
        )
    normalized = pattern.replace("\\", "/")
    return f"{relative_dir}/{normalized}" if normalized else relative_dir


def _matches_any(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch(relative, pattern) for pattern in patterns)


def write_default_config(root: Path) -> list[Path]:
    written: list[Path] = []
    config_path = root / ".ai-doc.yaml"
    eval_dir = root / ".ai-doc" / "evals"
    if not config_path.exists():
        config_path.write_text(_default_yaml(), encoding="utf-8")
        written.append(config_path)
    eval_dir.mkdir(parents=True, exist_ok=True)
    scenario_path = eval_dir / "basic.yaml"
    if not scenario_path.exists():
        scenario_path.write_text(_default_eval_yaml(), encoding="utf-8")
        written.append(scenario_path)
    return written


def _default_yaml() -> str:
    return read_text_resource("default.ai-doc.yaml")


def _default_eval_yaml() -> str:
    return read_text_resource("default-eval.yaml")


def assert_no_unknown_keys(data: dict[str, Any]) -> None:
    AiDocConfig.model_validate(data)
