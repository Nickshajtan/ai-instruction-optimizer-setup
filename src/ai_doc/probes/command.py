from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario
from ai_doc.domain.probes import BehavioralObservation, ProbeMode, ProbeUsage

TARGET_COMMAND_ENV = "AI_DOC_TARGET_COMMAND"
DEFAULT_TARGET_TIMEOUT_SECONDS = 120


class TargetProbeError(RuntimeError):
    pass


class _InstructionPayload(BaseModel):
    path: str
    text: str


class _TargetPlanRequest(BaseModel):
    mode: ProbeMode = ProbeMode.PLAN
    scenario: EvaluationScenario
    instructions: list[_InstructionPayload] = Field(default_factory=list)


class _TargetPlanResponse(BaseModel):
    target: str
    model: str | None = None
    model_version: str | None = None
    applicable_rules: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    forbidden_actions_avoided: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    usage: ProbeUsage = Field(default_factory=ProbeUsage)
    raw_summary: dict[str, object] = Field(default_factory=dict)


class CommandTargetProbe:
    """Run a real target-model planning probe through a provider-neutral command contract."""

    def __init__(self, command: str | None = None, *, timeout_seconds: int = DEFAULT_TARGET_TIMEOUT_SECONDS) -> None:
        self.command = command or os.getenv(TARGET_COMMAND_ENV, "")
        self.timeout_seconds = timeout_seconds
        if not self.command.strip():
            raise TargetProbeError(f"Target probe command is not configured; set {TARGET_COMMAND_ENV}.")

    def run(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> BehavioralObservation:
        request = _TargetPlanRequest(
            scenario=scenario,
            instructions=[
                _InstructionPayload(path=document.relative_path, text=document.text) for document in snapshot.documents
            ],
        )
        try:
            completed = subprocess.run(
                shlex.split(self.command, posix=os.name != "nt"),
                input=request.model_dump_json(),
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds,
                cwd=Path(snapshot.root),
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TargetProbeError(f"Target probe command failed to start or timed out: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise TargetProbeError(f"Target probe command failed: {detail}")
        try:
            response = _TargetPlanResponse.model_validate(json.loads(completed.stdout))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise TargetProbeError(f"Target probe command returned invalid JSON: {exc}") from exc
        return BehavioralObservation(
            target=response.target,
            model=response.model,
            model_version=response.model_version,
            scenario_id=scenario.id,
            context_paths=[document.relative_path for document in snapshot.documents],
            applicable_rules=response.applicable_rules,
            planned_actions=response.planned_actions,
            forbidden_actions_avoided=response.forbidden_actions_avoided,
            uncertainties=response.uncertainties,
            usage=response.usage,
            raw_summary=response.raw_summary,
        )
