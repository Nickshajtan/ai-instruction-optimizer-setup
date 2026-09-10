from __future__ import annotations

from dataclasses import dataclass

import ai_doc.optional_dependencies as optional_dependencies
from ai_doc.config.models import EvaluationEngine
from ai_doc.optional_dependencies import (
    DependencyStatus,
    install_missing_for_engine,
    missing_dependencies_for_engine,
)


@dataclass
class FakeDependency:
    name: str = "Fake"
    engine: EvaluationEngine = EvaluationEngine.PROMPTFOO
    requirement: str = "fake-package"
    available: bool = False
    checks: int = 0

    def status(self) -> DependencyStatus:
        self.checks += 1
        return DependencyStatus(
            name=self.name,
            available=self.available,
            detail=None if self.available else "missing",
            install_hint="install fake-package",
        )


class FakeInstaller:
    def __init__(self) -> None:
        self.installed: list[str] = []

    def install(self, requirement: str) -> None:
        self.installed.append(requirement)


def test_missing_dependencies_uses_registered_dependency(monkeypatch) -> None:
    dependency = FakeDependency()
    monkeypatch.setitem(
        optional_dependencies.DEPENDENCIES_BY_ENGINE,
        EvaluationEngine.PROMPTFOO,
        dependency,
    )

    missing = missing_dependencies_for_engine(EvaluationEngine.PROMPTFOO)

    assert missing == [
        DependencyStatus(
            name="Fake",
            available=False,
            detail="missing",
            install_hint="install fake-package",
        )
    ]
    assert dependency.checks == 1


def test_install_missing_for_engine_installs_registered_requirement(monkeypatch) -> None:
    dependency = FakeDependency(available=True)
    installer = FakeInstaller()
    monkeypatch.setitem(
        optional_dependencies.DEPENDENCIES_BY_ENGINE,
        EvaluationEngine.PROMPTFOO,
        dependency,
    )

    installed = install_missing_for_engine(EvaluationEngine.PROMPTFOO, installer)

    assert installed == ["fake-package"]
    assert installer.installed == ["fake-package"]
    assert dependency.checks == 1
