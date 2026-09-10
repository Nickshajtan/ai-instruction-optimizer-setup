from __future__ import annotations

import json
import os
import shlex
import subprocess
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field

SEMANTIC_COMMAND_ENV = "AI_DOC_SEMANTIC_COMMAND"


class ProviderUsage(BaseModel):
    requests: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    cost_source: str = "provider"
    cache_hits: int = 0


class SemanticResponse(BaseModel):
    data: dict[str, object] = Field(default_factory=dict)
    usage: ProviderUsage = Field(default_factory=ProviderUsage)


class SemanticProvider(Protocol):
    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse: ...


class SemanticBudgetExceeded(RuntimeError):
    pass


class BudgetedSemanticProvider:
    """Stop external work once reported request, token, or cost budgets are exhausted."""

    def __init__(
        self,
        provider: SemanticProvider,
        max_requests: int,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
        max_cost_usd: Decimal | None = None,
    ) -> None:
        self.provider = provider
        self.max_requests = max_requests
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_cost_usd = max_cost_usd
        self.usage = ProviderUsage(requests=0)

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        self._assert_can_start()
        response = self.provider.invoke(operation, payload)
        self.usage = ProviderUsage(
            requests=self.usage.requests + response.usage.requests,
            input_tokens=self.usage.input_tokens + response.usage.input_tokens,
            output_tokens=self.usage.output_tokens + response.usage.output_tokens,
            cost_usd=self.usage.cost_usd + response.usage.cost_usd,
            cost_source=response.usage.cost_source,
            cache_hits=self.usage.cache_hits + response.usage.cache_hits,
        )
        if self.usage.requests > self.max_requests:
            raise SemanticBudgetExceeded("semantic provider reported more requests than the configured budget permits")
        return response

    def _assert_can_start(self) -> None:
        if self.usage.requests >= self.max_requests:
            raise SemanticBudgetExceeded("semantic provider request budget exhausted")
        if self.max_input_tokens is not None and self.usage.input_tokens >= self.max_input_tokens:
            raise SemanticBudgetExceeded("semantic provider input-token budget exhausted")
        if self.max_output_tokens is not None and self.usage.output_tokens >= self.max_output_tokens:
            raise SemanticBudgetExceeded("semantic provider output-token budget exhausted")
        if self.max_cost_usd is not None and self.usage.cost_usd >= self.max_cost_usd:
            raise SemanticBudgetExceeded("semantic provider cost budget exhausted")


class CommandSemanticProvider:
    """Production provider-neutral adapter using a JSON stdin/stdout command contract."""

    def __init__(self, command: str | None = None) -> None:
        self.command: str = command or os.getenv(SEMANTIC_COMMAND_ENV) or ""
        if not self.command:
            raise RuntimeError(
                f"Semantic provider is not configured. Set {SEMANTIC_COMMAND_ENV} "
                "to a command that accepts JSON stdin."
            )

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        request = {"operation": operation, "payload": payload}
        completed = subprocess.run(
            shlex.split(self.command),
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Semantic provider failed ({completed.returncode}): {completed.stderr.strip()}")
        try:
            return SemanticResponse.model_validate_json(completed.stdout)
        except ValueError as exc:
            raise RuntimeError("Semantic provider returned invalid JSON contract") from exc
