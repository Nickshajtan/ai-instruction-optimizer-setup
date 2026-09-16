from __future__ import annotations

import ai_doc.tokens.counter as counter_module
from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG
from ai_doc.tokens.counter import OptionalModelAwareTokenCounter


class FallbackCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def count(self, text: str, model: str | None = None) -> int:
        self.calls.append((text, model))
        return 42


class FixedTokenCounter:
    label = "fixed-test"

    def count(self, text: str, model: str | None = None) -> int:
        del text, model
        return 5


class FakeEncoding:
    def encode(self, text: str) -> list[int]:
        return list(range(len(text.split())))


class FakeTiktoken:
    def encoding_for_model(self, model_name: str) -> FakeEncoding:
        if model_name == "unknown-model":
            raise KeyError(model_name)
        return FakeEncoding()


def test_model_aware_counter_uses_tiktoken_when_available(monkeypatch) -> None:
    fallback = FallbackCounter()
    monkeypatch.setattr(counter_module, "_load_tiktoken", lambda: FakeTiktoken())

    count = OptionalModelAwareTokenCounter(fallback=fallback).count("one two three", "known-model")

    assert count == 3
    assert fallback.calls == []


def test_model_aware_counter_falls_back_when_tiktoken_missing(monkeypatch) -> None:
    fallback = FallbackCounter()
    monkeypatch.setattr(counter_module, "_load_tiktoken", lambda: None)

    count = OptionalModelAwareTokenCounter(fallback=fallback).count("one two three", "known-model")

    assert count == 42
    assert fallback.calls == [("one two three", "known-model")]


def test_model_aware_counter_falls_back_for_unknown_model(monkeypatch) -> None:
    fallback = FallbackCounter()
    monkeypatch.setattr(counter_module, "_load_tiktoken", lambda: FakeTiktoken())

    count = OptionalModelAwareTokenCounter(fallback=fallback).count("one two three", "unknown-model")

    assert count == 42
    assert fallback.calls == [("one two three", "unknown-model")]


def test_static_check_accepts_injected_token_counter(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("short docs", encoding="utf-8")

    report = run_static_check(tmp_path, DEFAULT_CONFIG, token_counter=FixedTokenCounter())

    assert report.token_counter == "fixed-test"
    assert report.total_tokens == 5
