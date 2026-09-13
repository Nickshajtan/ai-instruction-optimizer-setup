import json
from pathlib import Path
from types import SimpleNamespace

from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import EvaluationScenario
from ai_doc.domain.probes import ExecutionStatus
from ai_doc.probes.execution import CommandExecutionProbe


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


def test_command_execution_probe_normalizes_response(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["request"] = json.loads(kwargs["input"])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "target": "codex",
                    "model": "gpt-test",
                    "model_version": "1",
                    "status": "succeeded",
                    "performed_actions": ["Run PHPUnit."],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": "0.001"},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("ai_doc.probes.execution.subprocess.run", fake_run)
    scenario = EvaluationScenario(id="php-change", task="Change a PHP module")

    observation = CommandExecutionProbe("fake-target --execute").run(tmp_path, _snapshot(tmp_path), scenario)

    assert captured["command"] == ["fake-target", "--execute"]
    assert captured["cwd"] == tmp_path
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["mode"] == "execute"
    assert observation.status == ExecutionStatus.SUCCEEDED
    assert observation.usage.input_tokens == 100
