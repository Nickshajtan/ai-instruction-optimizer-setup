from pathlib import Path

from tools.check_quality_contracts import find_deleted_parameters


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_reports_explicitly_deleted_parameter(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "def optimize(suite, candidate):\n"
        "    del suite\n"
        "    return candidate\n",
    )

    findings = find_deleted_parameters(path)

    assert len(findings) == 1
    assert "optimize" in findings[0]
    assert "suite" in findings[0]


def test_allows_deleting_non_parameter_local(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "def optimize(candidate):\n"
        "    temporary = candidate\n"
        "    del temporary\n"
        "    return candidate\n",
    )

    assert find_deleted_parameters(path) == []
