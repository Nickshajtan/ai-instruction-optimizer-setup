from __future__ import annotations

from ai_doc.providers.base import GenerationRequest, LLMProvider, T


class UnavailableLLMProvider(LLMProvider):
    def generate_structured(self, request: GenerationRequest, schema: type[T]) -> T:
        del request, schema
        raise RuntimeError("No LLM provider is configured for structured generation.")
