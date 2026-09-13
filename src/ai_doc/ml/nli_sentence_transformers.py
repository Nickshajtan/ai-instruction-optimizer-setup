from __future__ import annotations

from importlib import import_module
from typing import Any

from ai_doc.ml.base import NLIRelation, NLIResult
from ai_doc.ml.model_paths import NLI_MODEL_SLOT, resolve_local_model_reference
from ai_doc.ml.sentence_transformers import LocalModelUnavailableError


class SentenceTransformersNLIEngine:
    def __init__(self, model_name: str) -> None:
        model_reference = resolve_local_model_reference(model_name, NLI_MODEL_SLOT)
        try:
            module = import_module("sentence_transformers")
            model_type = module.CrossEncoder
            self._model: Any = model_type(model_reference, local_files_only=True)
        except (ImportError, OSError, ValueError) as exc:
            raise LocalModelUnavailableError(
                f"Local NLI model '{model_name}' is unavailable; install ai-doc[ml] and provision "
                "the model through an explicit path, AI_DOC_MODEL_ROOT, a bundled executable model, or the local cache."
            ) from exc

    def classify(self, premise: str, hypothesis: str) -> NLIResult:
        scores = self._model.predict([(premise, hypothesis)], apply_softmax=True)[0]
        labels = _labels(self._model)
        if len(labels) != len(scores):
            raise LocalModelUnavailableError("NLI label mapping does not match prediction dimensions.")
        index = max(range(len(scores)), key=lambda item: float(scores[item]))
        return NLIResult(relation=_relation(labels[index]), confidence=float(scores[index]))


def _labels(model: Any) -> list[str]:
    config = getattr(getattr(model, "model", None), "config", None)
    raw = getattr(config, "id2label", None)
    if not isinstance(raw, dict) or not raw:
        raise LocalModelUnavailableError("NLI model does not expose an id2label mapping.")
    result: list[str] = []
    for index in sorted(int(key) for key in raw):
        result.append(str(raw.get(index, raw.get(str(index)))).strip().lower())
    return result


def _relation(label: str) -> NLIRelation:
    if "contrad" in label:
        return NLIRelation.CONTRADICTION
    if "entail" in label:
        return NLIRelation.ENTAILMENT
    if "neutral" in label:
        return NLIRelation.NEUTRAL
    raise LocalModelUnavailableError(f"Unsupported NLI label: {label}")
