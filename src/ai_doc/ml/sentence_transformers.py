from __future__ import annotations

from typing import Any

from ai_doc.ml.base import NLIResult, NLIRelation


class LocalModelUnavailableError(RuntimeError):
    pass


def _load_sentence_transformer() -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def _load_cross_encoder() -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder


class SentenceTransformerSimilarityEngine:
    def __init__(self, model_name: str) -> None:
        try:
            model_type = _load_sentence_transformer()
            self._model: Any = model_type(model_name, local_files_only=True)
        except (ImportError, OSError, ValueError) as exc:
            raise LocalModelUnavailableError(
                f"Local similarity model '{model_name}' is unavailable. Install ai-doc[ml] and cache it locally first."
            ) from exc

    def similarity(self, left: str, right: str) -> float:
        embeddings = self._model.encode([left, right], normalize_embeddings=True)
        first, second = embeddings[0], embeddings[1]
        return float(sum(float(a) * float(b) for a, b in zip(first, second, strict=True)))


class SentenceTransformersNLIEngine:
    def __init__(self, model_name: str) -> None:
        try:
            model_type = _load_cross_encoder()
            self._model: Any = model_type(model_name, local_files_only=True)
        except (ImportError, OSError, ValueError) as exc:
            raise LocalModelUnavailableError(
                f"Local NLI model '{model_name}' is unavailable. Install ai-doc[ml] and cache it locally first."
            ) from exc

    def classify(self, premise: str, hypothesis: str) -> NLIResult:
        scores = self._model.predict([(premise, hypothesis)])[0]
        labels = _normalized_labels(self._model)
        if len(labels) != len(scores):
            raise LocalModelUnavailableError("NLI model label mapping does not match prediction dimensions.")
        index = max(range(len(scores)), key=lambda item: float(scores[item]))
        return NLIResult(relation=_relation_for_label(labels[index]), confidence=float(scores[index]))


def _normalized_labels(model: Any) -> list[str]:
    config = getattr(getattr(model, "model", None), "config", None)
    raw = getattr(config, "id2label", None)
    if not isinstance(raw, dict) or not raw:
        raise LocalModelUnavailableError("NLI model does not expose an id2label mapping.")
    labels: list[str] = []
    for index in sorted(int(key) for key in raw):
        value = raw.get(index, raw.get(str(index)))
        labels.append(str(value).strip().lower())
    return labels


def _relation_for_label(label: str) -> NLIRelation:
    if "contrad" in label:
        return NLIRelation.CONTRADICTION
    if "entail" in label:
        return NLIRelation.ENTAILMENT
    if "neutral" in label:
        return NLIRelation.NEUTRAL
    raise LocalModelUnavailableError(f"Unsupported NLI label: {label}")
