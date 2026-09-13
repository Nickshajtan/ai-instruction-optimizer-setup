from __future__ import annotations

from importlib import import_module
from typing import Any

from ai_doc.ml.model_paths import SIMILARITY_MODEL_SLOT, resolve_local_model_reference


class LocalModelUnavailableError(RuntimeError):
    pass


class SentenceTransformerSimilarityEngine:
    def __init__(self, model_name: str) -> None:
        model_reference = resolve_local_model_reference(model_name, SIMILARITY_MODEL_SLOT)
        try:
            module = import_module("sentence_transformers")
            model_type = module.SentenceTransformer
            self._model: Any = model_type(model_reference, local_files_only=True)
        except (ImportError, OSError, ValueError) as exc:
            raise LocalModelUnavailableError(
                f"Local similarity model '{model_name}' is unavailable; install ai-doc[ml] and provision "
                "the model through an explicit path, AI_DOC_MODEL_ROOT, a bundled executable model, or the local cache."
            ) from exc

    def similarity(self, left: str, right: str) -> float:
        embeddings = self._model.encode([left, right], normalize_embeddings=True)
        first, second = embeddings[0], embeddings[1]
        return float(sum(float(a) * float(b) for a, b in zip(first, second, strict=True)))
