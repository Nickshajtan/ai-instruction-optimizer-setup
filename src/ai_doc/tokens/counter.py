from __future__ import annotations

import re
from enum import StrEnum
from importlib import import_module
from typing import Protocol, cast


class TokenCountAccuracy(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class TokenCounter(Protocol):
    label: str

    def count(self, text: str, model: str | None = None) -> int: ...


APPROXIMATE_TOKEN_RATIO = 0.75
DEFAULT_TOKENIZER_MODEL = "gpt-4o-mini"


class TiktokenEncoding(Protocol):
    def encode(self, text: str) -> list[int]: ...


class TiktokenModule(Protocol):
    def encoding_for_model(self, model_name: str) -> TiktokenEncoding: ...


class ApproximateTokenCounter:
    label = "approximate"
    accuracy = TokenCountAccuracy.ESTIMATED

    def count(self, text: str, _model: str | None = None) -> int:
        segments = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        return max(1, int(len(segments) * APPROXIMATE_TOKEN_RATIO)) if text.strip() else 0


class OptionalModelAwareTokenCounter:
    label = "openai-tiktoken"
    accuracy = TokenCountAccuracy.MIXED

    def __init__(self, fallback: TokenCounter | None = None) -> None:
        self.fallback = fallback or ApproximateTokenCounter()

    def count(self, text: str, model: str | None = None) -> int:
        tiktoken = _load_tiktoken()
        if tiktoken is None:
            return self.fallback.count(text, model)
        try:
            encoding = tiktoken.encoding_for_model(model or DEFAULT_TOKENIZER_MODEL)
        except (KeyError, ValueError):
            return self.fallback.count(text, model)
        return len(encoding.encode(text))


def _load_tiktoken() -> TiktokenModule | None:
    try:
        module = import_module("tiktoken")
    except ImportError:
        return None
    return cast(TiktokenModule, module)


def token_count_accuracy(token_counter: TokenCounter) -> TokenCountAccuracy:
    raw = getattr(token_counter, "accuracy", TokenCountAccuracy.UNKNOWN)
    try:
        return TokenCountAccuracy(raw)
    except ValueError:
        return TokenCountAccuracy.UNKNOWN
