from decimal import Decimal

from ai_doc.config.models import PricingConfig
from ai_doc.tokens.pricing import estimate_input_cost, estimate_output_cost


def test_estimate_input_cost_returns_none_without_pricing() -> None:
    assert estimate_input_cost(1000, None) is None


def test_estimate_output_cost_returns_none_without_pricing() -> None:
    assert estimate_output_cost(1000, None) is None


def test_estimate_input_cost_uses_input_rate() -> None:
    pricing = PricingConfig(input_per_million=Decimal("2.50"), output_per_million=Decimal("10.00"))

    assert estimate_input_cost(2000, pricing) == Decimal("0.005")


def test_estimate_output_cost_uses_output_rate() -> None:
    pricing = PricingConfig(input_per_million=Decimal("2.50"), output_per_million=Decimal("10.00"))

    assert estimate_output_cost(2000, pricing) == Decimal("0.02")
