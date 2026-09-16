from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ai_doc.domain.documents import DocumentationSnapshot
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.extensions.process import PROTOCOL_VERSION, ProcessEvaluator, ProcessExtensionError


def _snapshot(text: str = "docs") -> DocumentationSnapshot:
    return DocumentationSnapshot.model_validate(
        {
            "root": ".",
            "documents": [
                {
                    "path": "AGENTS.md",
                    "relative_path": "AGENTS.md",
                    "profile": "instruction",
                    "text": text,
                    "token_count": 4,
                }
            ],
        }
    )


def _suite() -> EvaluationSuite:
    return EvaluationSuite.model_validate({"scenarios": [{"id": "smoke", "task": "Read docs."}]})


def _extension_script(tmp_path: Path, mode: str) -> Path:
    script = tmp_path / f"extension_{mode}.py"
    script.write_text(
        f"""
from __future__ import annotations

import json
import sys
import time

mode = {mode!r}
request = sys.stdin.read()

if mode == "timeout":
    time.sleep(2)
if mode == "nonzero":
    print("boom", file=sys.stderr)
    raise SystemExit(9)
if mode == "invalid-json":
    print("not json")
    raise SystemExit(0)

data = json.loads(request)
if mode == "wrong-protocol":
    protocol = "ai-doc.extension/v0"
else:
    protocol = data["protocol"]
response = {{"protocol": protocol, "request_id": data["request_id"]}}

if data["protocol"] != {PROTOCOL_VERSION!r}:
    response.update({{"status": "error", "error": "bad protocol"}})
elif data["operation"] != "evaluate":
    response.update({{"status": "error", "error": "bad operation"}})
elif mode == "explicit-error":
    response.update({{"status": "error", "error": {{"code": "denied", "message": "nope"}}}})
elif mode == "malformed-result":
    response.update({{"status": "ok", "result": {{"passed": True, "cases": [{{}}]}}}})
else:
    scenario_id = data["payload"]["suite"]["scenarios"][0]["id"]
    response.update(
        {{
            "status": "ok",
            "result": {{
                "engine": "external-fixture",
                "passed": True,
                "cases": [{{"id": scenario_id, "passed": True, "score": 0.9}}],
                "raw_summary": {{"semantic": True}},
            }},
        }}
    )
print(json.dumps(response))
""",
        encoding="utf-8",
    )
    return script


def _evaluator(tmp_path: Path, mode: str, timeout: float = 1) -> ProcessEvaluator:
    return ProcessEvaluator([sys.executable, str(_extension_script(tmp_path, mode))], timeout=timeout)


def test_process_evaluator_round_trips_valid_protocol(tmp_path: Path) -> None:
    result = _evaluator(tmp_path, "ok").evaluate(_snapshot(), None, _suite())

    assert result.engine == "external-fixture"
    assert result.passed is True
    assert result.cases[0].id == "smoke"


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("nonzero", "exited with status 9"),
        ("invalid-json", "invalid JSON"),
        ("wrong-protocol", "Unsupported process extension protocol"),
        ("malformed-result", "schema validation"),
        ("explicit-error", "returned an error"),
    ],
)
def test_process_evaluator_reports_protocol_failures(tmp_path: Path, mode: str, message: str) -> None:
    with pytest.raises(ProcessExtensionError, match=message):
        _evaluator(tmp_path, mode).evaluate(_snapshot(), None, _suite())


def test_process_evaluator_reports_timeout(tmp_path: Path) -> None:
    with pytest.raises(ProcessExtensionError, match="timed out"):
        _evaluator(tmp_path, "timeout", timeout=0.01).evaluate(_snapshot(), None, _suite())


def test_process_evaluator_reports_missing_executable() -> None:
    with pytest.raises(ProcessExtensionError, match="could not start"):
        ProcessEvaluator(["missing-ai-doc-extension-executable"]).evaluate(_snapshot(), None, _suite())
