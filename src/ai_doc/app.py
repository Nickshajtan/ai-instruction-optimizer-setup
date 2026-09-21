from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext, sort_findings
from ai_doc.analyzers.duplication import estimate_duplicate_tokens
from ai_doc.analyzers.finops import calculate_context_cost
from ai_doc.analyzers.suite import run_analyzers
from ai_doc.composition import resolve_token_counter
from ai_doc.config.models import AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.domain.findings import Finding, FindingSeverity
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.reporting.models import CheckReport, FindingAudit, FindingAuditEvent
from ai_doc.tokens.counter import TokenCounter, token_count_accuracy


def run_static_check(
    root: Path,
    config: AiDocConfig,
    profile: DocumentProfile | None = None,
    extensions: ExtensionRegistry | None = None,
    token_counter: TokenCounter | None = None,
) -> CheckReport:
    counter = token_counter or resolve_token_counter(config, extensions)
    snapshot = discover_markdown(root, config, counter)
    if profile:
        snapshot = snapshot.model_copy(
            update={"documents": tuple(doc for doc in snapshot.documents if doc.profile == profile)}
        )
    graph = DocumentGraph(snapshot)
    accuracy = token_count_accuracy(counter)
    context = AnalysisContext(
        config=config,
        snapshot=snapshot,
        graph=graph,
        token_counter=counter.label,
        token_count_accuracy=accuracy.value,
    )
    findings = run_analyzers(context)
    builtin_snapshots = [_finding_snapshot(finding) for finding in findings]
    builtin_error_count = sum(snapshot.severity == FindingSeverity.ERROR for snapshot in builtin_snapshots)
    audit_events: list[FindingAuditEvent] = []
    if extensions:
        for analyzer in extensions.analyzers:
            findings.extend(analyzer.analyze(context))
        for adapter in extensions.finding_adapters:
            before = [_finding_snapshot(finding) for finding in findings]
            findings = adapter.adapt_findings(context, findings)
            after = [_finding_snapshot(finding) for finding in findings]
            audit_events.extend(_adapter_audit_events(_adapter_identifier(adapter), builtin_snapshots, before, after))
        findings = sort_findings(findings)
    duplicate_tokens = estimate_duplicate_tokens(context)
    cost = calculate_context_cost(context, duplicate_tokens)
    return CheckReport(
        files_analyzed=len(snapshot.documents),
        total_tokens=snapshot.total_tokens,
        token_counter=counter.label,
        token_count_accuracy=accuracy.value,
        context_cost=cost,
        profiles={doc.relative_path: doc.profile.value for doc in snapshot.documents},
        findings=findings,
        finding_audit=FindingAudit(
            builtin_error_count=builtin_error_count,
            adapter_events=audit_events,
        ),
    )


def load_suite(root: Path) -> EvaluationSuite:
    return load_evaluation_suite(root)


def has_blocking_static_errors(report: CheckReport) -> bool:
    return any(finding.severity == FindingSeverity.ERROR for finding in report.findings) or (
        report.finding_audit.builtin_error_count > 0
    )


@dataclass(frozen=True)
class _FindingSnapshot:
    object_id: int
    code: str
    category: str
    severity: FindingSeverity
    path: str
    section: str | None
    message: str

    @property
    def stable_identity(self) -> tuple[str, str, str, str | None, str]:
        return (self.code, self.category, self.path, self.section, self.message)


def _adapter_audit_events(
    adapter: str,
    builtin_findings: list[_FindingSnapshot],
    before: list[_FindingSnapshot],
    after: list[_FindingSnapshot],
) -> list[FindingAuditEvent]:
    before_by_object = {finding.object_id: finding for finding in before}
    after_by_object = {finding.object_id: finding for finding in after}
    after_by_stable_identity = {finding.stable_identity: finding for finding in after}
    builtin_objects = {finding.object_id for finding in builtin_findings}
    events: list[FindingAuditEvent] = []
    for identity in builtin_objects:
        finding = before_by_object.get(identity)
        if finding is None:
            continue
        adapted = after_by_object.get(identity) or after_by_stable_identity.get(finding.stable_identity)
        if adapted is None:
            events.append(_audit_event(adapter, finding, "suppressed"))
        elif finding.severity != adapted.severity:
            events.append(_audit_event(adapter, finding, "severity_changed"))
    for identity, finding in before_by_object.items():
        if identity not in after_by_object and identity not in builtin_objects:
            events.append(_audit_event(adapter, finding, "suppressed_extension"))
    return events


def _finding_snapshot(finding: Finding) -> _FindingSnapshot:
    return _FindingSnapshot(
        object_id=id(finding),
        code=finding.code,
        category=finding.category.value,
        severity=finding.severity,
        path=finding.path,
        section=finding.section,
        message=finding.message,
    )


def _adapter_identifier(adapter: object) -> str:
    adapter_type = type(adapter)
    return f"{adapter_type.__module__}.{adapter_type.__qualname__}"


def _audit_event(adapter: str, finding: _FindingSnapshot, action: str) -> FindingAuditEvent:
    return FindingAuditEvent(
        adapter=adapter,
        code=finding.code,
        severity=finding.severity.value,
        path=finding.path,
        section=finding.section,
        action=action,
    )
