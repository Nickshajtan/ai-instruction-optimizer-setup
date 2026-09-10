from pathlib import Path

from ai_doc.diagnostics import build_doctor_report, runtime_mode
from ai_doc.resource_loader import read_text_resource
from ai_doc.root import discover_project_root


def test_root_discovery_from_nested_unicode_path(tmp_path: Path) -> None:
    project = tmp_path / "space path" / "проєкт"
    nested = project / "modules" / "foo"
    nested.mkdir(parents=True)
    (project / ".ai-doc.yaml").write_text("version: 1\ninclude: []\n", encoding="utf-8")
    assert discover_project_root(nested) == project.resolve()


def test_resource_templates_are_available() -> None:
    default_config = read_text_resource("default.ai-doc.yaml")
    assert "version: 1" in default_config
    assert ".tools/ai-doc/**" in default_config
    assert "basic-routing" in read_text_resource("default-eval.yaml")


def test_doctor_report_has_runtime_mode(tmp_path: Path) -> None:
    report = build_doctor_report(tmp_path)
    assert report.version
    assert runtime_mode() in {"source checkout", "installed package", "standalone executable"}
