from __future__ import annotations

import hashlib
import json
import re

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.probes import (
    ExecutionObservation,
    ExecutionProbe,
    ExecutionProbeReport,
    ExecutionStatus,
    ProbeExpectationKind,
    ProbeExpectationOutcome,
    ProbeExpectationResult,
    VerifiedExecutionObservation,
)
from ai_doc.evaluators.context import ContextSelector, DeterministicContextSelector
from ai_doc.ml.base import NLIEngine, NLIRelation
from ai_doc.ml.sentence_transformers import LocalModelUnavailableError
from ai_doc.probes.workspace import compare_manifests, isolated_workspace, workspace_manifest

NORMALIZE_RE = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


class ExecutionActionVerifier:
    def __init__(self, nli_engine: NLIEngine | None = None, *, confidence_threshold: float = 0.90) -> None:
        self.nli_engine = nli_engine
        self.confidence_threshold = confidence_threshold

    def verify(
        self,
        observation: ExecutionObservation,
        scenario: EvaluationScenario,
    ) -> list[ProbeExpectationResult]:
        results = [self._required(expectation, observation) for expectation in scenario.behavior_required]
        results.extend(self._forbidden(expectation, observation) for expectation in scenario.behavior_forbidden)
        return results

    def _required(self, expectation: str, observation: ExecutionObservation) -> ProbeExpectationResult:
        match = self._match(expectation, observation.performed_actions)
        if match is None:
            return _result(expectation, ProbeExpectationKind.REQUIRED, ProbeExpectationOutcome.UNCERTAIN, None, None)
        evidence, confidence, verifier = match
        return _result(
            expectation,
            ProbeExpectationKind.REQUIRED,
            ProbeExpectationOutcome.SATISFIED,
            evidence,
            confidence,
            verifier,
        )

    def _forbidden(self, expectation: str, observation: ExecutionObservation) -> ProbeExpectationResult:
        performed = self._match(expectation, observation.performed_actions)
        if performed is not None:
            evidence, confidence, verifier = performed
            return _result(
                expectation,
                ProbeExpectationKind.FORBIDDEN,
                ProbeExpectationOutcome.VIOLATED,
                evidence,
                confidence,
                verifier,
            )
        avoided = self._match(expectation, observation.forbidden_actions_avoided)
        if avoided is not None:
            evidence, confidence, verifier = avoided
            return _result(
                expectation,
                ProbeExpectationKind.FORBIDDEN,
                ProbeExpectationOutcome.SATISFIED,
                evidence,
                confidence,
                verifier,
            )
        return _result(expectation, ProbeExpectationKind.FORBIDDEN, ProbeExpectationOutcome.UNCERTAIN, None, None)

    def _match(self, expectation: str, actions: list[str]) -> tuple[str, float, str] | None:
        exact = _lexical_match(expectation, actions)
        if exact is not None:
            return exact, 1.0, "exact"
        if self.nli_engine is None:
            return None
        best_action: str | None = None
        best_confidence = 0.0
        for action in actions:
            try:
                result = self.nli_engine.classify(action, expectation)
            except LocalModelUnavailableError:
                return None
            if (
                result.relation == NLIRelation.ENTAILMENT
                and result.confidence >= self.confidence_threshold
                and (best_action is None or result.confidence > best_confidence)
            ):
                best_action = action
                best_confidence = result.confidence
        if best_action is None:
            return None
        return best_action, best_confidence, "nli"


class ExecutionProbeRunner:
    def __init__(
        self,
        probe: ExecutionProbe,
        verifier: ExecutionActionVerifier,
        selector: ContextSelector | None = None,
    ) -> None:
        self.probe = probe
        self.verifier = verifier
        self.selector = selector or DeterministicContextSelector()

    def run(self, snapshot: DocumentationSnapshot, suite: EvaluationSuite) -> ExecutionProbeReport:
        observations: list[VerifiedExecutionObservation] = []
        for scenario in suite.scenarios:
            selected = self.selector.select(snapshot, scenario)
            with isolated_workspace(snapshot.root) as workspace_root:
                before = workspace_manifest(workspace_root)
                observation = self.probe.run(workspace_root, selected, scenario)
                after = workspace_manifest(workspace_root)
            observation.workspace_delta = compare_manifests(before, after)
            _cross_check_workspace_evidence(observation)
            observation.cache_key = execution_cache_key(selected, scenario, observation)
            observations.append(
                VerifiedExecutionObservation(
                    observation=observation,
                    expectations=self.verifier.verify(observation, scenario),
                )
            )
        return ExecutionProbeReport(observations=observations)


def execution_cache_key(
    snapshot: DocumentationSnapshot,
    scenario: EvaluationScenario,
    observation: ExecutionObservation,
) -> str:
    payload = {
        "mode": observation.mode.value,
        "target": observation.target,
        "model": observation.model,
        "model_version": observation.model_version,
        "scenario": scenario.model_dump(mode="json"),
        "documents": [
            {"path": document.relative_path, "text": document.text}
            for document in sorted(snapshot.documents, key=lambda item: item.relative_path)
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lexical_match(expectation: str, actions: list[str]) -> str | None:
    expected = _normalize(expectation)
    if not expected:
        return None
    for action in actions:
        normalized = _normalize(action)
        if expected == normalized or expected in normalized or normalized in expected:
            return action
    return None


def _normalize(text: str) -> str:
    return " ".join(NORMALIZE_RE.sub(" ", text.casefold()).split())


def _cross_check_workspace_evidence(observation: ExecutionObservation) -> None:
    changed_paths = observation.workspace_delta.changed_paths
    if not changed_paths or observation.performed_actions:
        return
    paths = ", ".join(changed_paths)
    observation.uncertainties.append(
        "Workspace files changed but the target reported no performed actions; "
        f"changed paths: {paths}."
    )
    if observation.status == ExecutionStatus.SUCCEEDED:
        observation.status = ExecutionStatus.UNCERTAIN


def _result(
    expectation: str,
    kind: ProbeExpectationKind,
    outcome: ProbeExpectationOutcome,
    evidence: str | None,
    confidence: float | None,
    verifier: str = "exact",
) -> ProbeExpectationResult:
    return ProbeExpectationResult(
        expectation=expectation,
        kind=kind,
        outcome=outcome,
        evidence=evidence,
        confidence=confidence,
        verifier=verifier,
    )
