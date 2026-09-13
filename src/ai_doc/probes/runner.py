from __future__ import annotations

import hashlib
import json

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.probes import (
    BehavioralObservation,
    ObservationVerifier,
    PlanningProbeComparison,
    PlanningProbeReport,
    ScenarioProbeComparison,
    TargetProbe,
    VerifiedObservation,
)
from ai_doc.evaluators.context import ContextSelector, DeterministicContextSelector


class PlanningProbeRunner:
    def __init__(
        self,
        probe: TargetProbe,
        verifier: ObservationVerifier,
        selector: ContextSelector | None = None,
    ) -> None:
        self.probe = probe
        self.verifier = verifier
        self.selector = selector or DeterministicContextSelector()

    def run(self, snapshot: DocumentationSnapshot, suite: EvaluationSuite) -> PlanningProbeReport:
        observations: list[VerifiedObservation] = []
        for scenario in suite.scenarios:
            selected = self.selector.select(snapshot, scenario)
            observation = self.probe.run(selected, scenario)
            observation.cache_key = observation_cache_key(selected, scenario, observation)
            observations.append(
                VerifiedObservation(
                    observation=observation,
                    expectations=self.verifier.verify(observation, scenario),
                )
            )
        return PlanningProbeReport(observations=observations)


def compare_planning_reports(
    baseline: PlanningProbeReport,
    candidate: PlanningProbeReport,
) -> PlanningProbeComparison:
    baseline_by_id = {item.observation.scenario_id: item for item in baseline.observations}
    candidate_by_id = {item.observation.scenario_id: item for item in candidate.observations}
    scenario_ids = sorted(baseline_by_id.keys() & candidate_by_id.keys())
    scenarios = [
        ScenarioProbeComparison(
            scenario_id=scenario_id,
            baseline_violations=baseline_by_id[scenario_id].violations,
            candidate_violations=candidate_by_id[scenario_id].violations,
            baseline_satisfied=baseline_by_id[scenario_id].satisfied,
            candidate_satisfied=candidate_by_id[scenario_id].satisfied,
        )
        for scenario_id in scenario_ids
    ]
    return PlanningProbeComparison(baseline=baseline, candidate=candidate, scenarios=scenarios)


def observation_cache_key(
    snapshot: DocumentationSnapshot,
    scenario: EvaluationScenario,
    observation: BehavioralObservation,
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
