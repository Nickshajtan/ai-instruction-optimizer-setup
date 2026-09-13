from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.probes import BehavioralObservation, ProbeExpectationOutcome
from ai_doc.ml.base import NLIRelation, NLIResult
from ai_doc.probes.command import CommandTargetProbe
from ai_doc.probes.runner import PlanningProbeRunner, compare_planning_reports, observation_cache_key
from ai_doc.probes.verification import PlanningObservationVerifier


class FakeNLI:
    def __init__(self, result: NLIResult) -> None:
        self.result = result

    def classify(self, _premise: str, _hypothesis: str) -> NLIResult:
        return self.result


class FakeProbe:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, snapshot: DocumentationSnapshot, scenario: EvaluationScenario) -> BehavioralObservation:
        self.calls += 1
        return BehavioralObservation(
            target="codex",
            model="gpt-test",
            model_version="1",
            scenario_id=scenario.id,
            context_paths=[item.relative_path for item in snapshot.documents],
            planned_actions=["Run PHPUnit for the changed module."],
            forbidden_actions_avoided=["Do not edit generated files directly."],
        )


def _snapshot(tmp_path: Path, text: str = "# Rules\nRun PHPUnit.\n") -> DocumentationSnapshot:
    document = Document(
        path=tmp_path / "AGENTS.md",
        relative_path="AGENTS.md",
        profile=DocumentProfile.INSTRUCTION,
        text=text,
        token_count=4,
    )
    return DocumentationSnapshot(root=tmp_path, documents=(document,))


def _scenario() -> EvaluationScenario:
    return EvaluationScenario(
        id="php-change",
        task="Change a PHP module",
        expected_required=["Run PHPUnit for the changed module."],
        expected_forbidden=["Do not edit generated files directly."],
    )


def test_exact_verifier_marks_required_and_avoided_forbidden_as_satisfied() -> None:
    observation = BehavioralObservation(
        target="codex",
        scenario_id="php-change",
        planned_actions=["Run PHPUnit for the changed module."],
        forbidden_actions_avoided=["Do not edit generated files directly."],
    )

    results = PlanningObservationVerifier().verify(observation, _scenario())

    assert [item.outcome for item in results] == [
        ProbeExpectationOutcome.SATISFIED,
        ProbeExpectationOutcome.SATISFIED,
    ]


def test_verifier_marks_forbidden_planned_action_as_violation() -> None:
    observation = BehavioralObservation(
        target="codex",
        scenario_id="php-change",
        planned_actions=["Edit generated files directly."],
    )
    scenario = EvaluationScenario(
        id="generated",
        task="Fix generated output",
        expected_forbidden=["Edit generated files directly."],
    )

    result = PlanningObservationVerifier().verify(observation, scenario)[0]

    assert result.outcome == ProbeExpectationOutcome.VIOLATED


def test_nli_can_verify_semantically_equivalent_required_action() -> None:
    observation = BehavioralObservation(
        target="codex",
        scenario_id="php-change",
        planned_actions=["Execute the PHP unit-test suite."],
    )
    nli = FakeNLI(NLIResult(relation=NLIRelation.ENTAILMENT, confidence=0.96))

    result = PlanningObservationVerifier(nli).verify(observation, _scenario())[0]

    assert result.outcome == ProbeExpectationOutcome.SATISFIED
    assert result.verifier == "nli"
    assert result.confidence == 0.96


def test_runner_calls_target_once_per_scenario_and_assigns_cache_key(tmp_path: Path) -> None:
    probe = FakeProbe()
    runner = PlanningProbeRunner(probe, PlanningObservationVerifier())
    suite = EvaluationSuite(scenarios=[_scenario(), _scenario().model_copy(update={"id": "php-change-2"})])

    report = runner.run(_snapshot(tmp_path), suite)

    assert probe.calls == 2
    assert len(report.observations) == 2
    assert all(item.observation.cache_key for item in report.observations)


def test_cache_key_is_stable_and_changes_with_document_content(tmp_path: Path) -> None:
    scenario = _scenario()
    observation = BehavioralObservation(
        target="codex",
        model="gpt-test",
        model_version="1",
        scenario_id=scenario.id,
    )
    first = observation_cache_key(_snapshot(tmp_path), scenario, observation)
    again = observation_cache_key(_snapshot(tmp_path), scenario, observation)
    changed = observation_cache_key(_snapshot(tmp_path, "# Rules\nNever skip PHPUnit.\n"), scenario, observation)

    assert first == again
    assert first != changed


def test_report_comparison_keeps_scenario_level_counts(tmp_path: Path) -> None:
    runner = PlanningProbeRunner(FakeProbe(), PlanningObservationVerifier())
    suite = EvaluationSuite(scenarios=[_scenario()])

    baseline = runner.run(_snapshot(tmp_path), suite)
    candidate = runner.run(_snapshot(tmp_path), suite)
    comparison = compare_planning_reports(baseline, candidate)

    assert comparison.scenarios[0].scenario_id == "php-change"
    assert comparison.scenarios[0].baseline_violations == 0
    assert comparison.scenarios[0].candidate_violations == 0


def test_command_target_probe_uses_json_stdin_and_normalizes_response(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["request"] = json.loads(kwargs["input"])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "target": "codex",
                    "model": "gpt-test",
                    "model_version": "1",
                    "planned_actions": ["Run PHPUnit for the changed module."],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": "0.001"},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("ai_doc.probes.command.subprocess.run", fake_run)

    observation = CommandTargetProbe("fake-target --plan").run(_snapshot(tmp_path), _scenario())

    assert captured["command"] == ["fake-target", "--plan"]
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["mode"] == "plan"
    assert request["scenario"]["id"] == "php-change"
    assert request["instructions"][0]["path"] == "AGENTS.md"
    assert observation.target == "codex"
    assert observation.usage.input_tokens == 100
