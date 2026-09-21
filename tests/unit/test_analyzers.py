from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext
from ai_doc.analyzers.suite import run_analyzers
from ai_doc.app import run_static_check
from ai_doc.config.models import DEFAULT_CONFIG, AiDocConfig, LoadingConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.tokens.counter import ApproximateTokenCounter


def test_static_findings_include_clarity_and_duplication(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "- MUST validate changes.\n"
        "- Use best practices.\n"
        "- Repeat this operational rule.\n"
        "- Repeat this operational rule.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)
    codes = {finding.code for finding in report.findings}
    assert "CLARITY_AMBIGUOUS_RULE" in codes
    assert "FINOPS_DUPLICATE_LIST_ITEM" in codes


def test_modal_vocabulary_allows_different_uppercase_and_lowercase_terms(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "Extensions MUST preserve public contracts.\n"
        "Adapters should keep diagnostics concise.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)

    assert "CLARITY_INCONSISTENT_MODAL_VOCABULARY" not in {finding.code for finding in report.findings}


def test_modal_vocabulary_reports_same_term_in_uppercase_and_lowercase(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# Rules\n\n"
        "Extensions MUST preserve public contracts.\n"
        "Project adapters must use public API imports.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, DEFAULT_CONFIG)
    modal_findings = [finding for finding in report.findings if finding.code == "CLARITY_INCONSISTENT_MODAL_VOCABULARY"]

    assert len(modal_findings) == 1
    assert modal_findings[0].evidence == {"terms": ["must"]}


def test_repeated_headingless_list_item_collapses_to_one_duplicate_finding(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "- Always validate migrations before deployment.\n"
        "- Always validate migrations before deployment.\n"
        "- Always validate migrations before deployment.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, _config(include=["notes.md"], profiles={"notes.md": "instruction"}))

    duplicates = [finding for finding in report.findings if finding.code == "FINOPS_DUPLICATE_LIST_ITEM"]

    assert len(duplicates) == 1
    assert duplicates[0].evidence["occurrences"] == 3
    assert duplicates[0].evidence["duplicate_scopes"] == 1


def test_unrelated_headingless_list_items_do_not_create_duplicate_findings(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "- Install dependencies before running local checks.\n"
        "- Run unit tests after changing optimizer behavior.\n"
        "- Deploy staging only after review approval.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, _config(include=["notes.md"], profiles={"notes.md": "instruction"}))

    assert "FINOPS_DUPLICATE_LIST_ITEM" not in {finding.code for finding in report.findings}


def test_cross_document_headingless_duplicate_remains_detectable(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("- Always validate migrations before deployment.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("- Always validate migrations before deployment.\n", encoding="utf-8")
    report = run_static_check(
        tmp_path,
        _config(include=["*.md"], profiles={"*.md": "instruction"}),
    )

    duplicates = [finding for finding in report.findings if finding.code == "FINOPS_DUPLICATE_LIST_ITEM"]

    assert len(duplicates) == 1
    assert duplicates[0].evidence["occurrences"] == 2
    assert duplicates[0].evidence["duplicate_scopes"] == 2


def test_repeated_occurrences_across_documents_do_not_emit_per_occurrence_flood(tmp_path: Path) -> None:
    repeated = "- Always validate migrations before deployment.\n"
    (tmp_path / "a.md").write_text(repeated * 3, encoding="utf-8")
    (tmp_path / "b.md").write_text(repeated * 2, encoding="utf-8")
    report = run_static_check(tmp_path, _config(include=["*.md"], profiles={"*.md": "instruction"}))

    duplicates = [finding for finding in report.findings if finding.code == "FINOPS_DUPLICATE_LIST_ITEM"]

    assert len(duplicates) == 1
    assert duplicates[0].evidence["occurrences"] == 5
    assert duplicates[0].evidence["duplicate_scopes"] == 2


def test_tiny_legitimate_headingless_checklist_does_not_report_structure_signal(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "\n".join(
            [
                "- Run tests.",
                "- Update changelog.",
                "- Open PR.",
            ]
        ),
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, _config(include=["notes.md"], profiles={"notes.md": "instruction"}))

    assert "STRUCTURE_NO_HEADINGS" not in {finding.code for finding in report.findings}


def test_small_headingless_reference_note_does_not_report_structure_signal(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text(
        "Release checklist context:\n\n"
        "- Tests are usually run locally.\n"
        "- Changelog entries are collected weekly.\n"
        "- Pull requests use normal review queues.\n",
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, _config(include=["note.md"], profiles={"note.md": "reference"}))

    assert "STRUCTURE_NO_HEADINGS" not in {finding.code for finding in report.findings}


def test_substantial_headingless_document_reports_structure_signal(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text(
        "Operational release notes for maintainers.\n\n"
        + "\n".join(
            [
                "- Always validate migrations before deployment because rollback procedures depend on "
                "schema state, generated artifacts, release-window timing, environment ownership, "
                "database backups, and rollback verification across staging and production.",
                "- Always run unit tests before completion because several extension adapters share "
                "the static-analysis path, optimizer gates, reporting contracts, observation output, "
                "and command-line failure semantics used by downstream automation.",
                "- Always update release notes before tagging because downstream teams review those "
                "notes for operational risk, migration timing, documentation changes, semantic-provider "
                "configuration, extension compatibility, and release ownership.",
                "- Always preserve documented public contracts because extension authors depend on "
                "stable imports, command behavior, JSON report fields, and configuration validation.",
            ]
        ),
        encoding="utf-8",
    )
    report = run_static_check(tmp_path, _config(include=["notes.md"], profiles={"notes.md": "instruction"}))

    assert "STRUCTURE_NO_HEADINGS" in {finding.code for finding in report.findings}


def test_noisy_headingless_duplicate_case_keeps_structure_signal(tmp_path: Path) -> None:
    repeated = (
        "- Always validate migrations before deployment because deployment safety depends on "
        "schema state, generated artifacts, release-window timing, rollback ownership, environment "
        "approval, database backup verification, extension compatibility, and release communication.\n"
    )
    (tmp_path / "notes.md").write_text(repeated * 5, encoding="utf-8")
    report = run_static_check(tmp_path, _config(include=["notes.md"], profiles={"notes.md": "instruction"}))

    codes = {finding.code for finding in report.findings}
    assert "STRUCTURE_NO_HEADINGS" in codes
    assert "FINOPS_DUPLICATE_LIST_ITEM" in codes


def test_tiny_headingless_fragment_does_not_report_structure_signal(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("Short note.\n", encoding="utf-8")
    report = run_static_check(tmp_path, _config(include=["note.md"], profiles={"note.md": "instruction"}))

    assert "STRUCTURE_NO_HEADINGS" not in {finding.code for finding in report.findings}


def test_auto_detected_skill_without_inbound_link_is_not_orphaned(tmp_path: Path) -> None:
    skill = tmp_path / ".ai" / "skills" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Review Skill\n\nUse this skill for review.\n", encoding="utf-8")
    report = run_static_check(tmp_path, DEFAULT_CONFIG)

    assert report.profiles[".ai/skills/review/SKILL.md"] == DocumentProfile.SKILL.value
    assert "STRUCTURE_ORPHANED_AI_DOC" not in {finding.code for finding in report.findings}


def test_instruction_without_inbound_link_still_reports_orphan(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "agent.md").write_text("# Agent\n\nRun validation.\n", encoding="utf-8")
    report = run_static_check(
        tmp_path,
        _config(include=["docs/*.md"], profiles={"docs/*.md": "instruction"}),
    )

    assert "STRUCTURE_ORPHANED_AI_DOC" in {finding.code for finding in report.findings}


def test_on_demand_loading_does_not_imply_runtime_reachability(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "agent.md").write_text("# Agent\n\nRun validation.\n", encoding="utf-8")
    config = _config(include=["docs/*.md"], profiles={"docs/*.md": "instruction"})
    config.loading = {"docs/*.md": LoadingConfig(mode="on_demand")}

    report = run_static_check(tmp_path, config)

    assert "STRUCTURE_ORPHANED_AI_DOC" in {finding.code for finding in report.findings}


class CustomAnalyzer:
    def analyze(self, context: AnalysisContext) -> list[Finding]:
        document = context.snapshot.documents[0]
        return [
            Finding(
                code="CUSTOM_SORTED",
                category=FindingCategory.RISK,
                severity=FindingSeverity.INFO,
                path=document.relative_path,
                message="Custom analyzer ran.",
            )
        ]


def test_run_analyzers_accepts_custom_analyzer_sequence(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\n\nCustom content.\n", encoding="utf-8")
    snapshot = discover_markdown(tmp_path, DEFAULT_CONFIG, ApproximateTokenCounter())
    context = AnalysisContext(config=DEFAULT_CONFIG, snapshot=snapshot, graph=DocumentGraph(snapshot))

    findings = run_analyzers(context, analyzers=[CustomAnalyzer()])

    assert [finding.code for finding in findings] == ["CUSTOM_SORTED"]


def _config(*, include: list[str], profiles: dict[str, str]) -> AiDocConfig:
    return DEFAULT_CONFIG.model_copy(
        update={
            "include": include,
            "exclude": [],
            "profiles": {pattern: DocumentProfile(profile) for pattern, profile in profiles.items()},
        },
        deep=True,
    )
