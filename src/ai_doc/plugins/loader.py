from __future__ import annotations

import hashlib
import importlib.util
import traceback
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol

from ai_doc.config.models import ExtensionConfig
from ai_doc.plugins.registry import ExtensionRegistry


class ExtensionError(RuntimeError):
    def __init__(self, location: str, reason: str, details: str | None = None) -> None:
        self.location = location
        self.reason = reason
        self.details = details
        message = f"Failed to load extension:\n{location}\n\nReason:\n{reason}"
        if details:
            message += f"\n\nDetails:\n{details}"
        super().__init__(message)


class ExtensionImporter(Protocol):
    def import_module(self, path: Path) -> ModuleType:
        ...


class ExtensionPathResolver:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, location: str) -> Path:
        path = Path(location)
        absolute = path if path.is_absolute() else self.root / path
        absolute = absolute.resolve()
        if not absolute.is_file():
            raise FileNotFoundError(f"Extension file does not exist: {absolute}")
        try:
            absolute.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Extension path must stay inside the project root.") from exc
        return absolute


class PythonExtensionImporter:
    def import_module(self, path: Path) -> ModuleType:
        name = f"ai_doc_project_extension_{self._module_id(path)}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import extension from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _module_id(self, path: Path) -> str:
        return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]


class ExtensionLoader:
    def __init__(
        self,
        root: Path,
        importer: ExtensionImporter | None = None,
        registry_factory: Callable[[], ExtensionRegistry] = ExtensionRegistry,
    ) -> None:
        self.resolver = ExtensionPathResolver(root)
        self.importer = importer or PythonExtensionImporter()
        self.registry_factory = registry_factory

    def load(self, configs: list[ExtensionConfig], debug: bool = False) -> ExtensionRegistry:
        registry = self.registry_factory()
        for config in configs:
            self._load_config(config, registry, debug)
        return registry

    def _load_config(
        self,
        config: ExtensionConfig,
        registry: ExtensionRegistry,
        debug: bool,
    ) -> None:
        location = config.path
        try:
            module = self.importer.import_module(self.resolver.resolve(location))
            self._register(module, registry)
        except Exception as exc:
            details = traceback.format_exc() if debug else None
            raise ExtensionError(location, str(exc), details) from exc

    def _register(self, module: ModuleType, registry: ExtensionRegistry) -> None:
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError("Extension must define register(registry).")
        register(registry)


def load_extensions(root: Path, configs: list[ExtensionConfig], debug: bool = False) -> ExtensionRegistry:
    return ExtensionLoader(root).load(configs, debug=debug)


def _load_path(root: Path, path: Path) -> ModuleType:
    resolver = ExtensionPathResolver(root)
    importer = PythonExtensionImporter()
    return importer.import_module(resolver.resolve(str(path)))
