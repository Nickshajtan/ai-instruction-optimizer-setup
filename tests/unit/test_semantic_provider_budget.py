from decimal import Decimal

from ai_doc.providers.semantic import BudgetedSemanticProvider, ProviderUsage, SemanticResponse


class FixedUsageProvider:
    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        assert operation == "evaluate"
        assert payload == {"candidate": "docs"}
        return SemanticResponse(
            data={"passed": True},
            usage=ProviderUsage(
                requests=1,
                input_tokens=5,
                output_tokens=3,
                cost_usd=Decimal("0.02"),
                cost_source="estimated",
                cache_hits=2,
            ),
        )


def test_budgeted_provider_accumulates_all_reported_usage_fields() -> None:
    provider = BudgetedSemanticProvider(FixedUsageProvider(), max_requests=3)

    provider.invoke("evaluate", {"candidate": "docs"})
    provider.invoke("evaluate", {"candidate": "docs"})

    assert provider.usage == ProviderUsage(
        requests=2,
        input_tokens=10,
        output_tokens=6,
        cost_usd=Decimal("0.04"),
        cost_source="estimated",
        cache_hits=4,
    )
