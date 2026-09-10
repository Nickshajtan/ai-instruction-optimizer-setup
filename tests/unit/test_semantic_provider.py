import pytest

from ai_doc.providers.semantic import (
    BudgetedSemanticProvider,
    ProviderUsage,
    SemanticBudgetExceeded,
    SemanticResponse,
)


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, operation: str, _payload: dict[str, object]) -> SemanticResponse:
        self.calls += 1
        return SemanticResponse(data={"operation": operation}, usage=ProviderUsage(requests=1))


def test_budgeted_provider_never_starts_request_beyond_limit() -> None:
    inner = FakeProvider()
    provider = BudgetedSemanticProvider(inner, max_requests=2)
    provider.invoke("one", {})
    provider.invoke("two", {})
    with pytest.raises(SemanticBudgetExceeded):
        provider.invoke("three", {})
    assert inner.calls == 2
    assert provider.usage.requests == 2
