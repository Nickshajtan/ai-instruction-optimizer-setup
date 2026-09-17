from decimal import Decimal
from types import SimpleNamespace

import pytest

from ai_doc.providers.semantic import (
    BudgetedSemanticProvider,
    CommandSemanticProvider,
    ProviderUsage,
    SemanticBudgetExceeded,
    SemanticResponse,
)


class FakeProvider:
    def __init__(self, usage: ProviderUsage | None = None) -> None:
        self.calls = 0
        self.usage = usage or ProviderUsage(requests=1)

    def invoke(self, operation: str, _payload: dict[str, object]) -> SemanticResponse:
        self.calls += 1
        return SemanticResponse(data={"operation": operation}, usage=self.usage)


def test_budgeted_provider_never_starts_request_beyond_limit() -> None:
    inner = FakeProvider()
    provider = BudgetedSemanticProvider(inner, max_requests=2)
    provider.invoke("one", {})
    provider.invoke("two", {})
    with pytest.raises(SemanticBudgetExceeded):
        provider.invoke("three", {})
    assert inner.calls == 2
    assert provider.usage.requests == 2


@pytest.mark.parametrize(
    ("kwargs", "usage"),
    [
        ({"max_input_tokens": 100}, ProviderUsage(requests=1, input_tokens=100)),
        ({"max_output_tokens": 20}, ProviderUsage(requests=1, output_tokens=20)),
        ({"max_cost_usd": Decimal("0.01")}, ProviderUsage(requests=1, cost_usd=Decimal("0.01"))),
    ],
)
def test_reported_usage_at_budget_prevents_next_external_call(
    kwargs: dict[str, object], usage: ProviderUsage
) -> None:
    inner = FakeProvider(usage)
    provider = BudgetedSemanticProvider(inner, max_requests=10, **kwargs)  # type: ignore[arg-type]
    provider.invoke("one", {})
    with pytest.raises(SemanticBudgetExceeded):
        provider.invoke("two", {})
    assert inner.calls == 1


def test_one_call_token_overrun_is_preserved_and_blocks_followup() -> None:
    inner = FakeProvider(ProviderUsage(requests=1, input_tokens=120, cost_usd=Decimal("0.02")))
    provider = BudgetedSemanticProvider(
        inner,
        max_requests=10,
        max_input_tokens=100,
        max_cost_usd=Decimal("0.01"),
    )
    provider.invoke("one", {})
    assert provider.usage.input_tokens == 120
    assert provider.usage.cost_usd == Decimal("0.02")
    with pytest.raises(SemanticBudgetExceeded):
        provider.invoke("two", {})
    assert inner.calls == 1


def test_command_semantic_provider_passes_timeout_to_subprocess(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(*_args: object, **kwargs: object) -> SimpleNamespace:
        calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout='{"data":{},"usage":{"requests":1}}', stderr="")

    monkeypatch.setattr("ai_doc.providers.semantic.subprocess.run", fake_run)

    CommandSemanticProvider("semantic-fixture", timeout=3.5).invoke("score", {})

    assert calls[0]["timeout"] == 3.5


def test_command_semantic_provider_reports_timeout(monkeypatch) -> None:
    def fake_timeout(*_args: object, **_kwargs: object) -> None:
        import subprocess

        raise subprocess.TimeoutExpired(cmd=["semantic-fixture"], timeout=2)

    monkeypatch.setattr("ai_doc.providers.semantic.subprocess.run", fake_timeout)

    with pytest.raises(RuntimeError, match="Semantic provider timed out after 2s"):
        CommandSemanticProvider("semantic-fixture", timeout=2).invoke("score", {})
