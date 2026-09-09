from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class GenerationRequest(BaseModel):
    system: str
    prompt: str
    model: str | None = None


class LLMProvider(Protocol):
    def generate_structured(self, request: GenerationRequest, schema: type[T]) -> T: ...
