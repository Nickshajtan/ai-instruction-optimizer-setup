from __future__ import annotations

import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

from pydantic import BaseModel

from ai_doc import __version__
from ai_doc.config.loader import ConfigError, load_config
from ai_doc.optional_dependencies import DependencyStatus, deepeval_status, promptfoo_status
from ai_doc.providers.semantic import SEMANTIC_COMMAND_ENV


class Capability(BaseModel):
    name: str
    status: str
    detail: str | None = None


class DoctorReport(BaseModel):
    version: str
    runtime_mode: str
    project_root: str
    core: list[Capability]
    runtime: list[Capability]
    optional_integrations: list[Capability]
    llm_providers: list[Capability]


def build_doctor_report(root: Path) -> DoctorReport:
    current_runtime_mode = runtime_mode()
    return DoctorReport(
        version=__version__,
        runtime_mode=current_runtime_mode,
        project_root=str(root),
        core=_core_capabilities(root),
        runtime=_runtime_capabilities(root, current_runtime_mode),
        optional_integrations=_optional_integration_capabilities(),
        llm_providers=_llm_provider_capabilities(),
    )


def runtime_mode() -> str:
    if getattr(sys, "frozen", False):
        return "standalone executable"
    path = Path(__file__).resolve()
    if ".tools" in path.parts:
        return "source checkout"
    if "site-packages" in path.parts:
        return "installed package"
    return "source checkout"


def _core_capabilities(root: Path) -> list[Capability]:
    core = [Capability(name="ai-doc", status="ok", detail=__version__)]
    try:
        load_config(root)
        core.append(Capability(name="configuration", status="ok", detail=str(root / ".ai-doc.yaml")))
    except ConfigError as exc:
        core.append(Capability(name="configuration", status="error", detail=str(exc)))
    core.append(Capability(name="static analyzer", status="ok"))
    return core


def _runtime_capabilities(root: Path, current_runtime_mode: str) -> list[Capability]:
    return [
        Capability(name="Python runtime", status="ok", detail=sys.version.split()[0]),
        Capability(name="runtime mode", status="ok", detail=current_runtime_mode),
        _writable_capability(root),
    ]


def _optional_integration_capabilities() -> list[Capability]:
    return [
        _local_ml_capability(),
        _capability_from_dependency(promptfoo_status()),
        _capability_from_dependency(deepeval_status()),
        Capability(
            name="semantic command",
            status="configured" if os.getenv(SEMANTIC_COMMAND_ENV) else "not configured",
            detail=SEMANTIC_COMMAND_ENV,
        ),
    ]


def _local_ml_capability() -> Capability:
    available = find_spec("sentence_transformers") is not None
    if available:
        return Capability(
            name="Local semantic ML",
            status="ok",
            detail="sentence-transformers importable; configured model artifacts must also exist locally",
        )
    return Capability(
        name="Local semantic ML",
        status="missing",
        detail='optional; install with `python -m pip install "ai-doc[ml]"`',
    )


def _llm_provider_capabilities() -> list[Capability]:
    return [
        Capability(name="OpenAI", status="configured" if os.getenv("OPENAI_API_KEY") else "not configured"),
        Capability(name="Anthropic", status="configured" if os.getenv("ANTHROPIC_API_KEY") else "not configured"),
    ]


def _writable_capability(root: Path) -> Capability:
    try:
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            Path(temporary).joinpath("probe").write_text("ok", encoding="utf-8")
        return Capability(name="writable output", status="ok", detail=str(root))
    except OSError as exc:
        return Capability(name="writable output", status="error", detail=str(exc))


def _capability_from_dependency(status: DependencyStatus) -> Capability:
    return Capability(
        name=status.name,
        status="ok" if status.available else "missing",
        detail=status.detail if status.available else f"{status.detail}; {status.install_hint}",
    )
