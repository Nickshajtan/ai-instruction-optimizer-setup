from pathlib import Path

from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG


def test_literal_contradiction_is_reported(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always validate changes.\n- Never validate changes.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)
    matches = [item for item in report.findings if item.code == "RISK_LITERAL_CONTRADICTION"]
    assert len(matches) == 1
    assert matches[0].evidence["proposition"] == "validate changes"


def test_different_propositions_are_not_reported(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n- Always run unit tests.\n- Never run integration tests.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)
    assert "RISK_LITERAL_CONTRADICTION" not in {item.code for item in report.findings}
