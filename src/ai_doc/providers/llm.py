from __future__ import annotations

from ai_doc.providers.base import GenerationRequest, LLMProvider, T


class UnavailableLLMProvider(LLMProvider):
    def generate_structured(self, _request: GenerationRequest, _schema: type[T]) -> T:
        raise RuntimeError("No LLM provider is configured for structured generation.")
