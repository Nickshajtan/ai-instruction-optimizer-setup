from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from ai_doc.domain.evaluations import EvaluationCaseResult, EvaluationResult
from ai_doc.domain.findings import Finding
from ai_doc.domain.proposals import CandidateProposal

ObjectiveName = Literal["reliability", "clarity", "always_loaded_tokens", "expected_context_tokens", "estimated_context_cost", "critical_invariant_recall"]

class CandidateStatus(StrEnum):
    GENERATED="generated"; EVALUATING="evaluating"; VALID="valid"; DOMINATED="dominated"; REJECTED="rejected"; FRONTIER="frontier"
class StopReason(StrEnum):
    GENERATION_COMPLETE="stopped_generation"; CANDIDATE_BUDGET="stopped_candidate_budget"; REQUEST_BUDGET="stopped_request_budget"; COST_BUDGET="stopped_budget"; TOKEN_BUDGET="stopped_token_budget"; PATIENCE="stopped_patience"

class ObjectiveVector(BaseModel):
    reliability: float | None = Field(default=None, ge=0, le=1); clarity: float = Field(ge=0, le=1); always_loaded_tokens: int
    expected_context_tokens: float | None = None; estimated_context_cost: Decimal | None = None; critical_invariant_recall: float = Field(ge=0, le=1)

class CandidateCost(BaseModel):
    deterministic_operations:int=0; generation_requests:int=0; evaluation_requests:int=0; prompt_suboptimizer_requests:int=0
    generation_input_tokens:int=0; generation_output_tokens:int=0; evaluation_input_tokens:int=0; evaluation_output_tokens:int=0
    prompt_suboptimizer_input_tokens:int=0; prompt_suboptimizer_output_tokens:int=0; cache_hits:int=0; total_cost:Decimal=Decimal("0")
    cost_sources:list[str]=Field(default_factory=list)
    @property
    def external_requests(self)->int: return self.generation_requests+self.evaluation_requests+self.prompt_suboptimizer_requests
    @property
    def input_tokens(self)->int: return self.generation_input_tokens+self.evaluation_input_tokens+self.prompt_suboptimizer_input_tokens
    @property
    def output_tokens(self)->int: return self.generation_output_tokens+self.evaluation_output_tokens+self.prompt_suboptimizer_output_tokens
RunCost=CandidateCost

class CandidateFingerprint(BaseModel):
    operations:tuple[str,...]; affected_sections:tuple[str,...]; extracted_targets:tuple[str,...]; content_hash:str
class EvalFailure(BaseModel):
    scenario_id:str; message:str|None=None; score:float|None=None
class OptimizationFeedback(BaseModel):
    candidate_id:str; strengths:list[str]=Field(default_factory=list); weaknesses:list[str]=Field(default_factory=list); failed_evals:list[EvalFailure]=Field(default_factory=list)
    clarity_findings:list[Finding]=Field(default_factory=list); finops_findings:list[Finding]=Field(default_factory=list); invariant_risks:list[str]=Field(default_factory=list)
    comparison_to_baseline:list[str]=Field(default_factory=list); comparison_to_frontier:list[str]=Field(default_factory=list); suggested_mutation_directions:list[str]=Field(default_factory=list)
class InvariantDecision(BaseModel):
    invariant_id:str; status:str; source:str
class CandidateEvidence(BaseModel):
    generation_reason:str|None=None; feedback:OptimizationFeedback|None=None; invariant_decisions:list[InvariantDecision]=Field(default_factory=list)
    effective_context:dict[str,list[str]]=Field(default_factory=dict); recommendation_reason:str|None=None
class Candidate(BaseModel):
    id:str; parent_ids:list[str]=Field(default_factory=list); strategy:str; proposal:CandidateProposal; objective_vector:ObjectiveVector|None=None
    evaluation:EvaluationResult|None=None; status:CandidateStatus=CandidateStatus.GENERATED; generation:int; creation_cost:RunCost=Field(default_factory=RunCost)
    fingerprint:CandidateFingerprint|None=None; rejection_reasons:list[str]=Field(default_factory=list); artifact_dir:str|None=None; evidence:CandidateEvidence=Field(default_factory=CandidateEvidence)
class CandidatePopulation(BaseModel):
    generation:int; candidates:list[Candidate]
class ParetoEntry(BaseModel):
    candidate_id:str; objective_vector:ObjectiveVector; generation:int; proposal_summary:list[str]; evaluation_references:list[str]=Field(default_factory=list); cost:RunCost=Field(default_factory=RunCost)
class ParetoArchive(BaseModel):
    entries:list[ParetoEntry]=Field(default_factory=list)
class SearchMemory(BaseModel):
    successful_patterns:list[str]=Field(default_factory=list); failed_patterns:list[str]=Field(default_factory=list); invariant_risks:list[str]=Field(default_factory=list); unexplored_opportunities:list[str]=Field(default_factory=list)
class OptimizationRun(BaseModel):
    run_id:str; strategy:str; seed:int|None=None; baseline_candidate_id:str="baseline"; candidates:list[Candidate]=Field(default_factory=list); frontier:ParetoArchive=Field(default_factory=ParetoArchive)
    recommended_candidate_id:str|None=None; recommendation_reason:str|None=None; search_memory:SearchMemory=Field(default_factory=SearchMemory); stopped_reason:StopReason|str
    total_cost:RunCost=Field(default_factory=RunCost); metadata:dict[str,object]=Field(default_factory=dict)

def passed_evaluation_score(evaluation:EvaluationResult|None)->float|None:
    if evaluation is None or not evaluation.cases: return None
    scores=[case.score for case in evaluation.cases if case.score is not None]
    return sum(scores)/len(scores) if scores else sum(1.0 for case in evaluation.cases if case.passed)/len(evaluation.cases)
def failed_cases(evaluation:EvaluationResult|None)->list[EvaluationCaseResult]:
    return [] if evaluation is None else [case for case in evaluation.cases if not case.passed]
