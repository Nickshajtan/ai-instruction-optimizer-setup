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
    """Enforce request budget before an external call and track reported usage."""

    def __init__(self, provider: SemanticProvider, max_requests: int) -> None:
        self.provider = provider
        self.max_requests = max_requests
        self.usage = ProviderUsage(requests=0)

    def invoke(self, operation: str, payload: dict[str, object]) -> SemanticResponse:
        if self.usage.requests >= self.max_requests:
            raise SemanticBudgetExceeded("semantic provider request budget exhausted")
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


class CommandSemanticProvider:
    """Production provider-neutral adapter using a JSON stdin/stdout command contract."""

    def __init__(self, command: str | None = None) -> None:
        self.command = command or os.getenv(SEMANTIC_COMMAND_ENV, "")
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
