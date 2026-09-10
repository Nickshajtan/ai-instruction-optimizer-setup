from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.config.models import ExtensionConfig
from ai_doc.domain.findings import Finding
from ai_doc.plugins.loader import ExtensionError, ExtensionLoader, ExtensionPathResolver
from ai_doc.plugins.registry import ExtensionRegistry


class FakeAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        del context
        return []


class FakeImporter:
    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self.paths: list[Path] = []

    def import_module(self, path: Path) -> ModuleType:
        self.paths.append(path)
        return self.module


def test_registry_validates_analyzer_contract() -> None:
    registry = ExtensionRegistry()

    registry.add_analyzer(FakeAnalyzer())

    assert len(registry.analyzers) == 1
    with pytest.raises(TypeError, match="analyze\\(context\\)"):
        registry.add_analyzer(object())


def test_extension_path_resolver_rejects_paths_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_extension.py"
    outside.write_text("def register(registry): pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="inside the project root"):
        ExtensionPathResolver(tmp_path).resolve(str(outside))


def test_extension_loader_imports_and_registers_extension(tmp_path: Path) -> None:
    extension_path = tmp_path / "extension.py"
    extension_path.write_text("", encoding="utf-8")
    module = ModuleType("fake_extension")

    def register(registry: ExtensionRegistry) -> None:
        registry.add_analyzer(FakeAnalyzer())

    module.register = register
    importer = FakeImporter(module)

    registry = ExtensionLoader(tmp_path, importer=importer).load(
        [ExtensionConfig(path="extension.py")]
    )

    assert importer.paths == [extension_path.resolve()]
    assert len(registry.analyzers) == 1


def test_extension_loader_wraps_registration_failure(tmp_path: Path) -> None:
    extension_path = tmp_path / "extension.py"
    extension_path.write_text("", encoding="utf-8")
    importer = FakeImporter(ModuleType("fake_extension"))

    with pytest.raises(ExtensionError, match="Extension must define register"):
        ExtensionLoader(tmp_path, importer=importer).load([ExtensionConfig(path="extension.py")])
