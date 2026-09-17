from __future__ import annotations

from decimal import Decimal

from ai_doc.config.models import PricingConfig


def estimate_input_cost(tokens: int, pricing: PricingConfig | None) -> Decimal | None:
    if pricing is None:
        return None
    return Decimal(tokens) * pricing.input_per_million / Decimal(1_000_000)


def estimate_output_cost(tokens: int, pricing: PricingConfig | None) -> Decimal | None:
    if pricing is None:
        return None
    return Decimal(tokens) * pricing.output_per_million / Decimal(1_000_000)
