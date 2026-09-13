from __future__ import annotations

import os
import sys
from pathlib import Path

MODEL_ROOT_ENV = "AI_DOC_MODEL_ROOT"
BUNDLED_MODEL_DIR = "ai_doc_models"
SIMILARITY_MODEL_SLOT = "similarity"
NLI_MODEL_SLOT = "nli"


def resolve_local_model_reference(model_reference: str, slot: str) -> str:
    """Resolve an explicitly local or vendored model before falling back to local HF cache lookup.

    The returned reference is always intended for local-only loading. Network fallback remains
    disabled by the concrete sentence-transformers adapters.
    """

    explicit = Path(model_reference).expanduser()
    if explicit.exists():
        return str(explicit.resolve())

    configured_root = os.getenv(MODEL_ROOT_ENV)
    if configured_root:
        candidate = Path(configured_root).expanduser() / slot
        if candidate.exists():
            return str(candidate.resolve())

    bundled_root = _bundled_root()
    if bundled_root is not None:
        candidate = bundled_root / slot
        if candidate.exists():
            return str(candidate)

    return model_reference


def _bundled_root() -> Path | None:
    pyinstaller_root = getattr(sys, "_MEIPASS", None)
    if pyinstaller_root:
        return Path(str(pyinstaller_root)) / BUNDLED_MODEL_DIR

    package_root = Path(__file__).resolve().parents[1]
    candidate = package_root / BUNDLED_MODEL_DIR
    return candidate if candidate.exists() else None
