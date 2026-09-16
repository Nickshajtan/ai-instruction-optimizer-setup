from __future__ import annotations

from ai_doc.analyzers.base import AnalysisContext, Analyzer
from ai_doc.domain.documents import Document, DocumentationSnapshot, DocumentProfile
from ai_doc.domain.evaluations import (
    EvaluationResult,
    Evaluator,
    PairwiseDimension,
    PairwiseDimensionResult,
    PairwiseOutcome,
    PairwiseSemanticEvaluator,
    PairwiseSemanticResult,
)
from ai_doc.domain.findings import Finding, FindingCategory, FindingSeverity
from ai_doc.domain.optimization import Candidate, ObjectiveVector
from ai_doc.domain.probes import (
    BehavioralObservation,
    ExecutionObservation,
    ExecutionObservationVerifier,
    ExecutionProbe,
    ExecutionProbeReport,
    ExecutionStatus,
    ObservationVerifier,
    PlanningProbeComparison,
    PlanningProbeReport,
    ProbeExpectationKind,
    ProbeExpectationOutcome,
    ProbeExpectationResult,
    ProbeMode,
    ProbeUsage,
    ScenarioProbeComparison,
    TargetProbe,
    VerifiedExecutionObservation,
    VerifiedObservation,
    WorkspaceDelta,
)
from ai_doc.extensions.process import PROTOCOL_VERSION, ProcessEvaluator, ProcessExtensionError, ProcessTransport
from ai_doc.optimizer.recommendation import RecommendationPolicy
from ai_doc.plugins.registry import ExtensionRegistry
from ai_doc.providers.base import LLMProvider
from ai_doc.tokens.counter import TokenCounter

__all__ = [
    "AnalysisContext",
    "Analyzer",
    "BehavioralObservation",
    "Candidate",
    "Document",
    "DocumentProfile",
    "DocumentationSnapshot",
    "EvaluationResult",
    "Evaluator",
    "ExecutionObservation",
    "ExecutionObservationVerifier",
    "ExecutionProbe",
    "ExecutionProbeReport",
    "ExecutionStatus",
    "ExtensionRegistry",
    "Finding",
    "FindingCategory",
    "FindingSeverity",
    "LLMProvider",
    "ObjectiveVector",
    "ObservationVerifier",
    "PairwiseDimension",
    "PairwiseDimensionResult",
    "PairwiseOutcome",
    "PairwiseSemanticEvaluator",
    "PairwiseSemanticResult",
    "PlanningProbeComparison",
    "PlanningProbeReport",
    "ProcessEvaluator",
    "ProcessExtensionError",
    "ProcessTransport",
    "PROTOCOL_VERSION",
    "ProbeExpectationKind",
    "ProbeExpectationOutcome",
    "ProbeExpectationResult",
    "ProbeMode",
    "ProbeUsage",
    "RecommendationPolicy",
    "ScenarioProbeComparison",
    "TargetProbe",
    "TokenCounter",
    "VerifiedExecutionObservation",
    "VerifiedObservation",
    "WorkspaceDelta",
]
