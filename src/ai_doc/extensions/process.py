from __future__ import annotations

import json
import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationResult, EvaluationSuite

PROTOCOL_VERSION = "ai-doc.extension/v1"
EVALUATE_OPERATION = "evaluate"
DEFAULT_TIMEOUT_SECONDS = 120.0


class ProcessExtensionError(RuntimeError):
    def __init__(self, reason: str, diagnostics: str | None = None) -> None:
        self.reason = reason
        self.diagnostics = diagnostics
        message = reason
        if diagnostics:
            message = f"{message}\n\nDiagnostics:\n{diagnostics}"
        super().__init__(message)


@dataclass(frozen=True)
class ProcessExtensionCommand:
    command: Sequence[str]
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    env: Mapping[str, str] = field(default_factory=dict)


class ProcessEvaluator:
    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
        engine: str = "process",
    ) -> None:
        if not command:
            raise ValueError("Process evaluator command must not be empty.")
        self.command = tuple(command)
        self.timeout = timeout
        self.env = dict(env or {})
        self.engine = engine

    def evaluate(
        self,
        baseline: DocumentationSnapshot,
        candidate: DocumentationSnapshot | None,
        suite: EvaluationSuite,
    ) -> EvaluationResult:
        request_id = uuid.uuid4().hex
        response = self._invoke(_evaluation_request(request_id, baseline, candidate, suite))
        return _evaluation_result_from_response(response, request_id, self.engine)

    def _invoke(self, request: dict[str, object]) -> dict[str, object]:
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
            raise ProcessExtensionError("Process extension response must be a JSON object.")
        return parsed


def _evaluation_request(
    request_id: str,
    baseline: DocumentationSnapshot,
    candidate: DocumentationSnapshot | None,
    suite: EvaluationSuite,
) -> dict[str, object]:
    return {
        "protocol": PROTOCOL_VERSION,
        "operation": EVALUATE_OPERATION,
        "request_id": request_id,
        "payload": {
            "baseline": _snapshot_payload(baseline),
            "candidate": _snapshot_payload(candidate) if candidate is not None else None,
            "suite": suite.model_dump(mode="json"),
        },
    }


def _snapshot_payload(snapshot: DocumentationSnapshot) -> dict[str, object]:
    return {
        "root": str(snapshot.root),
        "total_tokens": snapshot.total_tokens,
        "documents": [
            {
                "path": document.relative_path,
                "profile": document.profile.value,
                "text": document.text,
                "token_count": document.token_count,
            }
            for document in snapshot.documents
        ],
    }


def _evaluation_result_from_response(
    response: dict[str, object],
    request_id: str,
    default_engine: str,
) -> EvaluationResult:
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
    result = response.get("result")
    if not isinstance(result, dict):
        raise ProcessExtensionError("Process extension 'ok' response must contain an object result.")
    normalized: dict[str, Any] = {"engine": default_engine, **result}
    try:
        return EvaluationResult.model_validate(normalized)
    except ValidationError as exc:
        raise ProcessExtensionError(f"Process extension result failed schema validation:\n{exc}") from exc


def _limit_diagnostics(stderr: str | bytes | None, limit: int = 4000) -> str | None:
    if stderr is None:
        return None
    text = stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
    text = text.strip()
    if not text:
        return None
    return text[:limit]
