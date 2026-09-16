from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

PROTOCOL_VERSION = "ai-doc.extension/v1"
DEFAULT_TIMEOUT_SECONDS = 120.0
DIAGNOSTIC_LIMIT = 4000
DESCRIBE_OPERATION = "describe"


class ProcessExtensionError(RuntimeError):
    def __init__(self, reason: str, diagnostics: str | None = None) -> None:
        self.reason = reason
        self.diagnostics = diagnostics
        message = reason
        if diagnostics:
            message = f"{message}\n\nDiagnostics:\n{diagnostics}"
        super().__init__(message)


class ProcessTransport:
    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not command:
            raise ValueError("Process extension command must not be empty.")
        self.command = tuple(command)
        self.timeout = timeout
        self.env = dict(env or {})

    def invoke(self, operation: str, payload: Mapping[str, Any]) -> Any:
        if not operation:
            raise ValueError("Process extension operation must not be empty.")
        request_id = uuid.uuid4().hex
        request = {
            "protocol": PROTOCOL_VERSION,
            "operation": operation,
            "request_id": request_id,
            "payload": dict(payload),
        }
        response = self._invoke(request)
        return _result_from_response(response, request_id)

    def describe(self) -> Any:
        return self.invoke(DESCRIBE_OPERATION, {})

    def _invoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        payload = json.dumps(request, separators=(",", ":"))
        try:
            completed = subprocess.run(
                self.command,
                input=payload,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                shell=False,
                env=None if not self.env else {**os.environ, **self.env},
            )
        except FileNotFoundError as exc:
            raise ProcessExtensionError(f"Process extension could not start: {self.command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            diagnostics = _limit_diagnostics(exc.stderr)
            raise ProcessExtensionError(f"Process extension timed out after {self.timeout:g}s.", diagnostics) from exc
        if completed.returncode != 0:
            diagnostics = _limit_diagnostics(completed.stderr)
            raise ProcessExtensionError(
                f"Process extension exited with status {completed.returncode}.",
                diagnostics,
            )
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            diagnostics = _limit_diagnostics(completed.stderr)
            raise ProcessExtensionError("Process extension wrote invalid JSON to stdout.", diagnostics) from exc
        if not isinstance(parsed, dict):
            diagnostics = _limit_diagnostics(completed.stderr)
            raise ProcessExtensionError("Process extension response must be a JSON object.", diagnostics) from None
        return parsed


def _result_from_response(
    response: Mapping[str, Any],
    request_id: str,
) -> Any:
    protocol = response.get("protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProcessExtensionError(f"Unsupported process extension protocol {protocol!r}; expected {PROTOCOL_VERSION}.")
    if response.get("request_id") != request_id:
        raise ProcessExtensionError("Process extension response request_id did not match the request.")
    status = response.get("status")
    if status == "error":
        error = response.get("error")
        detail = error if isinstance(error, str) else json.dumps(error, sort_keys=True)
        raise ProcessExtensionError(f"Process extension returned an error: {detail}")
    if status != "ok":
        raise ProcessExtensionError("Process extension response status must be 'ok' or 'error'.")
    if "result" not in response:
        raise ProcessExtensionError("Process extension 'ok' response must contain a result.")
    return response["result"]


def _limit_diagnostics(stderr: str | bytes | None, limit: int = DIAGNOSTIC_LIMIT) -> str | None:
    if stderr is None:
        return None
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
    text = text.strip()
    if not text:
        return None
    return text[:limit]
