from __future__ import annotations

from pathlib import Path

from ai_doc.analyzers.base import AnalysisContext, sort_findings
from ai_doc.analyzers.duplication import estimate_duplicate_tokens
from ai_doc.analyzers.finops import calculate_context_cost
from ai_doc.analyzers.suite import run_analyzers
from ai_doc.config.models import AiDocConfig
from ai_doc.discovery.markdown_discovery import discover_markdown
from ai_doc.domain.documents import DocumentProfile
from ai_doc.domain.evaluations import EvaluationSuite
from ai_doc.evaluators.suite import load_evaluation_suite
from ai_doc.markdown.graph import DocumentGraph
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.reporting.models import CheckReport
from ai_doc.tokens.counter import ApproximateTokenCounter


def run_static_check(
    root: Path,
    config: AiDocConfig,
    profile: DocumentProfile | None = None,
    extensions: ExtensionRegistry | None = None,
) -> CheckReport:
    counter = ApproximateTokenCounter()
    snapshot = discover_markdown(root, config, counter)
    if profile:
        snapshot = snapshot.model_copy(
            update={"documents": tuple(doc for doc in snapshot.documents if doc.profile == profile)}
        )
    graph = DocumentGraph(snapshot)
    context = AnalysisContext(config=config, snapshot=snapshot, graph=graph)
    findings = run_analyzers(context)
    if extensions:
        for analyzer in extensions.analyzers:
            findings.extend(analyzer.analyze(context))
        findings = sort_findings(findings)
    duplicate_tokens = estimate_duplicate_tokens(context)
    cost = calculate_context_cost(context, duplicate_tokens)
    return CheckReport(
        files_analyzed=len(snapshot.documents),
        total_tokens=snapshot.total_tokens,
        token_counter=counter.label,
        context_cost=cost,
        profiles={doc.relative_path: doc.profile.value for doc in snapshot.documents},
        findings=findings,
    )


def load_suite(root: Path) -> EvaluationSuite:
    return load_evaluation_suite(root)
