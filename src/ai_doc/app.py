from __future__ import annotations

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
    builtin_findings = list(findings)
    audit_events: list[FindingAuditEvent] = []
    if extensions:
        for analyzer in extensions.analyzers:
            findings.extend(analyzer.analyze(context))
        for adapter in extensions.finding_adapters:
            before = list(findings)
            findings = adapter.adapt_findings(context, findings)
            audit_events.extend(_adapter_audit_events(builtin_findings, before, findings))
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
            builtin_error_count=sum(finding.severity == FindingSeverity.ERROR for finding in builtin_findings),
            adapter_events=audit_events,
        ),
    )


def load_suite(root: Path) -> EvaluationSuite:
    return load_evaluation_suite(root)


def has_blocking_static_errors(report: CheckReport) -> bool:
    return any(finding.severity == FindingSeverity.ERROR for finding in report.findings) or (
        report.finding_audit.builtin_error_count > 0
    )


def _adapter_audit_events(
    builtin_findings: list[Finding],
    before: list[Finding],
    after: list[Finding],
) -> list[FindingAuditEvent]:
    before_by_identity = {_finding_identity(finding): finding for finding in before}
    after_by_identity = {_finding_identity(finding): finding for finding in after}
    builtin_identities = {_finding_identity(finding) for finding in builtin_findings}
    events: list[FindingAuditEvent] = []
    for finding in builtin_findings:
        identity = _finding_identity(finding)
        adapted = after_by_identity.get(identity)
        if adapted is None:
            events.append(_audit_event(finding, "suppressed"))
        elif finding.severity != adapted.severity:
            events.append(_audit_event(finding, "severity_changed"))
    for identity, finding in before_by_identity.items():
        if identity not in after_by_identity and identity not in builtin_identities:
            events.append(_audit_event(finding, "suppressed_extension"))
    return events


def _finding_identity(finding: Finding) -> tuple[object, ...]:
    return (finding.code, finding.category, finding.path, finding.section, finding.message)


def _audit_event(finding: Finding, action: str) -> FindingAuditEvent:
    return FindingAuditEvent(
        code=finding.code,
        severity=finding.severity.value,
        path=finding.path,
        section=finding.section,
        action=action,
    )
