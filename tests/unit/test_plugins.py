from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.config.models import ExtensionConfig
from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite
from ai_doc.domain.findings import Finding
from ai_doc.plugins.loader import ExtensionError, ExtensionLoader, ExtensionPathResolver
from ai_doc.plugins.registry import ExtensionRegistry


class FakeAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        del context
        return []


class FakeEvaluator:
    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        del baseline, candidate, suite
        return EvaluationResult(engine="fake", passed=True)


class FakeTokenCounter:
    def count(self, text: str, model: str | None = None) -> int:
        del text, model
        return 7


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


def test_registry_registers_named_extension_contracts_deterministically() -> None:
    registry = ExtensionRegistry()

    registry.add_evaluator("quality", FakeEvaluator())
    registry.add_evaluator("fast", FakeEvaluator())
    registry.add_token_counter("fixed", FakeTokenCounter())

    assert [entry.name for entry in registry.evaluators] == ["fast", "quality"]
    assert registry.resolve_evaluator("quality").evaluate
    assert registry.resolve_token_counter("fixed").count("anything") == 7
    with pytest.raises(ValueError, match="Duplicate evaluator"):
        registry.add_evaluator("quality", FakeEvaluator())
    with pytest.raises(KeyError, match="Unknown evaluator"):
        registry.resolve_evaluator("missing")
    with pytest.raises(TypeError, match="evaluate"):
        registry.add_evaluator("broken", object())


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

    registry = ExtensionLoader(tmp_path, importer=importer).load([ExtensionConfig(path="extension.py")])

    assert importer.paths == [extension_path.resolve()]
    assert len(registry.analyzers) == 1


def test_extension_loader_wraps_registration_failure(tmp_path: Path) -> None:
    extension_path = tmp_path / "extension.py"
    extension_path.write_text("", encoding="utf-8")
    importer = FakeImporter(ModuleType("fake_extension"))

    with pytest.raises(ExtensionError, match="Extension must define register"):
        ExtensionLoader(tmp_path, importer=importer).load([ExtensionConfig(path="extension.py")])
