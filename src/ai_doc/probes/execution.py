from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario
from ai_doc.domain.probes import ExecutionObservation, ExecutionStatus, ProbeMode, ProbeUsage
from ai_doc.probes.command import (
    DEFAULT_TARGET_TIMEOUT_SECONDS,
    TARGET_COMMAND_ENV,
    TargetProbeError,
    split_command,
)


class _InstructionPayload(BaseModel):
    path: str
    text: str


class _TargetExecutionRequest(BaseModel):
    mode: ProbeMode = ProbeMode.EXECUTE
    scenario: EvaluationScenario
    instructions: list[_InstructionPayload] = Field(default_factory=list)


class _TargetExecutionResponse(BaseModel):
    target: str
    model: str | None = None
    model_version: str | None = None
    status: ExecutionStatus = ExecutionStatus.UNCERTAIN
    performed_actions: list[str] = Field(default_factory=list)
    forbidden_actions_avoided: list[str] = Field(default_factory=list)
    reported_checks: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    usage: ProbeUsage = Field(default_factory=ProbeUsage)
    raw_summary: dict[str, object] = Field(default_factory=dict)


class CommandExecutionProbe:
    """Run a real target-agent execution through the provider-neutral target command."""

    def __init__(self, command: str | None = None, *, timeout_seconds: int = DEFAULT_TARGET_TIMEOUT_SECONDS) -> None:
        resolved_command = command or os.getenv(TARGET_COMMAND_ENV) or ""
        if not resolved_command.strip():
            raise TargetProbeError(f"Target probe command is not configured; set {TARGET_COMMAND_ENV}.")
        self.command: str = resolved_command
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        workspace_root: Path,
        snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        request = _TargetExecutionRequest(
            scenario=scenario,
            instructions=[
                _InstructionPayload(path=document.relative_path, text=document.text) for document in snapshot.documents
            ],
        )
        try:
            completed = subprocess.run(
                split_command(self.command),
                input=request.model_dump_json(),
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                cwd=workspace_root,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TargetProbeError(f"Target execution command failed to start or timed out: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise TargetProbeError(f"Target execution command failed: {detail}")
        try:
            response = _TargetExecutionResponse.model_validate(json.loads(completed.stdout))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise TargetProbeError(f"Target execution command returned invalid JSON: {exc}") from exc
        return ExecutionObservation(
            target=response.target,
            model=response.model,
            model_version=response.model_version,
            scenario_id=scenario.id,
            context_paths=[document.relative_path for document in snapshot.documents],
            status=response.status,
            performed_actions=response.performed_actions,
            forbidden_actions_avoided=response.forbidden_actions_avoided,
            reported_checks=response.reported_checks,
            uncertainties=response.uncertainties,
            usage=response.usage,
            raw_summary=response.raw_summary,
        )
