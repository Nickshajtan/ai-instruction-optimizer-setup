from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Protocol

from ai_doc.config.models import EvaluationEngine

PROMPTFOO_REQUIREMENT = "promptfoo"
DEEPEVAL_REQUIREMENT = "deepeval>=1.0"
NODE_MINIMUM_VERSION = (22, 22, 0)


class OptionalDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str | None
    install_hint: str


class OptionalDependency(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def engine(self) -> EvaluationEngine:
        ...

    @property
    def requirement(self) -> str:
        ...

    def status(self) -> DependencyStatus:
        ...


@dataclass(frozen=True)
class PromptfooDependency:
    name: str = "Promptfoo"
    engine: EvaluationEngine = EvaluationEngine.PROMPTFOO
    requirement: str = PROMPTFOO_REQUIREMENT

    def status(self) -> DependencyStatus:
        executable = shutil.which("promptfoo")
        if not executable:
            return DependencyStatus(
                name=self.name,
                available=False,
                detail="missing CLI",
                install_hint='Install with `python -m pip install "ai-doc[promptfoo]"`.',
            )
        node_version = _node_version()
        if node_version is None:
            return DependencyStatus(
                name=self.name,
                available=False,
                detail=f"{executable}; Node.js missing",
                install_hint="Install Node.js 22.22.0 or newer, then rerun setup.",
            )
        if node_version < NODE_MINIMUM_VERSION:
            version = ".".join(str(part) for part in node_version)
            minimum = ".".join(str(part) for part in NODE_MINIMUM_VERSION)
            return DependencyStatus(
                name=self.name,
                available=False,
                detail=f"{executable}; Node.js {version} is below {minimum}",
                install_hint=f"Upgrade Node.js to {minimum} or newer, then rerun setup.",
            )
        return DependencyStatus(
            name=self.name,
            available=True,
            detail=f"{executable}; Node.js {'.'.join(str(part) for part in node_version)}",
            install_hint="",
        )


@dataclass(frozen=True)
class DeepEvalDependency:
    name: str = "DeepEval"
    engine: EvaluationEngine = EvaluationEngine.DEEPEVAL
    requirement: str = DEEPEVAL_REQUIREMENT

    def status(self) -> DependencyStatus:
        if find_spec("deepeval"):
            return DependencyStatus(
                name=self.name,
                available=True,
                detail="importable",
                install_hint="",
            )
        return DependencyStatus(
            name=self.name,
            available=False,
            detail="missing Python package",
            install_hint='Install with `python -m pip install "ai-doc[deepeval]"`.',
        )


OPTIONAL_DEPENDENCIES: tuple[OptionalDependency, ...] = (
    PromptfooDependency(),
    DeepEvalDependency(),
)
DEPENDENCIES_BY_ENGINE: dict[EvaluationEngine, OptionalDependency] = {
    dependency.engine: dependency for dependency in OPTIONAL_DEPENDENCIES
}


class PythonPackageInstaller:
    def install(self, requirement: str) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", requirement],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise OptionalDependencyError(
                f"Failed to install {requirement} with pip. {detail}"
            )


def promptfoo_status() -> DependencyStatus:
    return _dependency_for_engine(EvaluationEngine.PROMPTFOO).status()


def deepeval_status() -> DependencyStatus:
    return _dependency_for_engine(EvaluationEngine.DEEPEVAL).status()


def missing_dependencies_for_engine(engine: EvaluationEngine) -> list[DependencyStatus]:
    status = _dependency_for_engine(engine).status()
    return [] if status.available else [status]


def install_missing_for_engine(
    engine: EvaluationEngine,
    installer: PythonPackageInstaller | None = None,
) -> list[str]:
    installer = installer or PythonPackageInstaller()
    installed: list[str] = []
    for requirement in _requirements_for_engine(engine):
        installer.install(requirement)
        installed.append(requirement)
    missing = missing_dependencies_for_engine(engine)
    if missing:
        details = "; ".join(f"{item.name}: {item.detail}. {item.install_hint}" for item in missing)
        raise OptionalDependencyError(f"Optional dependency setup incomplete. {details}")
    return installed


def install_deep_dependencies(installer: PythonPackageInstaller | None = None) -> list[str]:
    installer = installer or PythonPackageInstaller()
    installed: list[str] = []
    for dependency in OPTIONAL_DEPENDENCIES:
        installer.install(dependency.requirement)
        installed.append(dependency.requirement)
    statuses = [dependency.status() for dependency in OPTIONAL_DEPENDENCIES]
    missing = [status for status in statuses if not status.available]
    if missing:
        details = "; ".join(f"{item.name}: {item.detail}. {item.install_hint}" for item in missing)
        raise OptionalDependencyError(f"Deep dependency setup incomplete. {details}")
    return installed


def _requirements_for_engine(engine: EvaluationEngine) -> tuple[str, ...]:
    return (_dependency_for_engine(engine).requirement,)


def _dependency_for_engine(engine: EvaluationEngine) -> OptionalDependency:
    try:
        return DEPENDENCIES_BY_ENGINE[engine]
    except KeyError as exc:
        raise OptionalDependencyError(f"Unsupported evaluation engine: {engine}") from exc


def _node_version() -> tuple[int, int, int] | None:
    executable = shutil.which("node")
    if not executable:
        return None
    completed = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", completed.stdout.strip())
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch
