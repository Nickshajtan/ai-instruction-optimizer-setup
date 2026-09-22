from pathlib import Path

from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationScenario, EvaluationSuite
from ai_doc.domain.probes import ExecutionObservation, ExecutionStatus, ProbeExpectationOutcome
from ai_doc.probes.execution_runner import ExecutionActionVerifier, ExecutionProbeRunner


class FakeExecutionProbe:
    def __init__(self) -> None:
        self.calls = 0

    def run(
        self,
        workspace_root: Path,
        snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        self.calls += 1
        (workspace_root / f"{scenario.id}.txt").write_text("changed", encoding="utf-8")
        return ExecutionObservation(
            target="codex",
            scenario_id=scenario.id,
            context_paths=[item.relative_path for item in snapshot.documents],
            status=ExecutionStatus.SUCCEEDED,
            performed_actions=["Run PHPUnit for the changed module."],
            forbidden_actions_avoided=["Edit generated files directly."],
        )


class UnreportedMutationProbe:
    def run(
        self,
        workspace_root: Path,
        _snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        (workspace_root / "unreported.txt").write_text("changed", encoding="utf-8")
        return ExecutionObservation(
            target="codex",
            scenario_id=scenario.id,
            status=ExecutionStatus.SUCCEEDED,
            performed_actions=[],
        )


class ReadOnlyProbe:
    def run(
        self,
        _workspace_root: Path,
        _snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        return ExecutionObservation(
            target="codex",
            scenario_id=scenario.id,
            status=ExecutionStatus.SUCCEEDED,
            performed_actions=[],
        )


class NoMutationActionProbe:
    def run(
        self,
        _workspace_root: Path,
        _snapshot: DocumentationSnapshot,
        scenario: EvaluationScenario,
    ) -> ExecutionObservation:
        return ExecutionObservation(
            target="codex",
            scenario_id=scenario.id,
            status=ExecutionStatus.SUCCEEDED,
            performed_actions=["Inspected the documentation without editing files."],
        )


def _snapshot(tmp_path: Path) -> DocumentationSnapshot:
    text = "# Rules\nRun PHPUnit.\n"
    path = tmp_path / "AGENTS.md"
    path.write_text(text, encoding="utf-8")
    document = Document(
        path=path,
        relative_path="AGENTS.md",
        profile=DocumentProfile.INSTRUCTION,
        text=text,
        token_count=4,
    )
    return DocumentationSnapshot(root=tmp_path, documents=(document,))


def _scenario(scenario_id: str = "php-change") -> EvaluationScenario:
    return EvaluationScenario(
        id=scenario_id,
        task="Change a PHP module",
        behavior_required=["Run PHPUnit for the changed module."],
        behavior_forbidden=["Edit generated files directly."],
    )


def test_execution_runner_measures_real_workspace_delta(tmp_path: Path) -> None:
    probe = FakeExecutionProbe()
    runner = ExecutionProbeRunner(probe, ExecutionActionVerifier())
    suite = EvaluationSuite(scenarios=[_scenario(), _scenario("php-change-2")])

    report = runner.run(_snapshot(tmp_path), suite)

    assert probe.calls == 2
    assert report.violations == 0
    assert report.satisfied == 4
    assert report.observations[0].observation.workspace_delta.created_paths == ["php-change.txt"]
    assert report.observations[0].observation.cache_key


def test_execution_runner_marks_unreported_workspace_mutation_uncertain(tmp_path: Path) -> None:
    runner = ExecutionProbeRunner(UnreportedMutationProbe(), ExecutionActionVerifier())

    report = runner.run(_snapshot(tmp_path), EvaluationSuite(scenarios=[_scenario()]))

    observation = report.observations[0].observation
    assert observation.workspace_delta.created_paths == ["unreported.txt"]
    assert observation.status == ExecutionStatus.UNCERTAIN
    assert "reported no performed actions" in observation.uncertainties[0]


def test_execution_runner_allows_read_only_execution_without_uncertainty(tmp_path: Path) -> None:
    runner = ExecutionProbeRunner(ReadOnlyProbe(), ExecutionActionVerifier())

    report = runner.run(_snapshot(tmp_path), EvaluationSuite(scenarios=[_scenario()]))

    observation = report.observations[0].observation
    assert observation.workspace_delta.changed_paths == []
    assert observation.status == ExecutionStatus.SUCCEEDED
    assert observation.uncertainties == []


def test_execution_runner_does_not_require_mutation_for_reported_read_action(tmp_path: Path) -> None:
    runner = ExecutionProbeRunner(NoMutationActionProbe(), ExecutionActionVerifier())

    report = runner.run(_snapshot(tmp_path), EvaluationSuite(scenarios=[_scenario()]))

    observation = report.observations[0].observation
    assert observation.workspace_delta.changed_paths == []
    assert observation.status == ExecutionStatus.SUCCEEDED
    assert observation.uncertainties == []


def test_execution_verifier_detects_forbidden_performed_action() -> None:
    observation = ExecutionObservation(
        target="codex",
        scenario_id="generated",
        performed_actions=["Edit generated files directly."],
    )
    scenario = EvaluationScenario(
        id="generated",
        task="Regenerate output",
        behavior_forbidden=["Edit generated files directly."],
    )

    result = ExecutionActionVerifier().verify(observation, scenario)[0]

    assert result.outcome == ProbeExpectationOutcome.VIOLATED
