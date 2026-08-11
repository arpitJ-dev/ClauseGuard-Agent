from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["LOW", "MEDIUM", "HIGH"]
VerifierStatus = Literal["verified", "not_run", "unavailable"]
SCHEMA_VERSION: Literal["1.0"] = "1.0"


class LoadedDocument(BaseModel):
    path: str
    file_type: str
    title: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LegalEntity(BaseModel):
    text: str
    label: str
    source: str = "heuristic"


class Clause(BaseModel):
    id: str
    order: int
    title: str
    text: str
    category: str = "General"
    risk_terms: List[str] = Field(default_factory=list)


class Evidence(BaseModel):
    id: str
    source: str
    title: str
    text: str
    relevance: float = Field(ge=0.0, le=1.0)
    clause_id: Optional[str] = None


class ComponentScores(BaseModel):
    deterministic_rules: float = Field(ge=0.0, le=1.0)
    rag_evidence: float = Field(ge=0.0, le=1.0)
    primary_reasoning: float = Field(ge=0.0, le=1.0)
    verifier_agreement: float = Field(ge=0.0, le=1.0)
    clause_structure: float = Field(ge=0.0, le=1.0)
    final: float = Field(ge=0.0, le=1.0)
    weights: Dict[str, float]


class CandidateFinding(BaseModel):
    id: str
    issue_type: str
    severity: Severity
    clause_id: Optional[str] = None
    clause_title: Optional[str] = None
    explanation: str
    rule_id: str = ""
    signals: List[str] = Field(default_factory=list)
    deterministic_score: float = Field(ge=0.0, le=1.0)
    structure_score: float = Field(ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list)
    primary_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verifier_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verifier_status: VerifierStatus = "not_run"
    verifier_rationale: str = ""


class Finding(BaseModel):
    id: str
    issue_type: str
    severity: Severity
    clause_id: Optional[str] = None
    clause_title: Optional[str] = None
    explanation: str
    rule_id: str = ""
    signals: List[str] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    component_scores: ComponentScores
    accepted: bool
    acceptance_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    model_confidence: float = Field(ge=0.0, le=1.0)
    verifier_confidence: float = Field(ge=0.0, le=1.0)
    verifier_status: VerifierStatus = "not_run"
    verifier_rationale: str = ""
    suggested_rewrite: Optional[str] = None


class Rewrite(BaseModel):
    clause_id: str
    original_text: str
    rewritten_text: str
    rationale: str


class AnalysisReport(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    document_id: str
    file_path: str
    title: str
    document_type: str
    summary: str
    clauses: List[Clause]
    entities: List[LegalEntity]
    evidence: List[Evidence]
    findings: List[Finding]
    rewrites: List[Rewrite]
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    limitations: List[str] = Field(
        default_factory=lambda: [
            "This system is a legal analysis assistant and not a lawyer replacement.",
            "Findings require review by a qualified legal professional.",
            "Coverage depends on the configured rule set, reference corpus, and document quality.",
        ]
    )


class ComparisonSummary(BaseModel):
    matched: int = Field(ge=0)
    changed: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)


class ClauseDelta(BaseModel):
    status: Literal["unchanged", "changed", "added", "removed"]
    similarity: float = Field(ge=0.0, le=1.0)
    original_clause_id: Optional[str] = None
    original_title: Optional[str] = None
    original_category: Optional[str] = None
    modified_clause_id: Optional[str] = None
    modified_title: Optional[str] = None
    modified_category: Optional[str] = None
    original_risk_terms: List[str] = Field(default_factory=list)
    modified_risk_terms: List[str] = Field(default_factory=list)
    original_preview: str = ""
    modified_preview: str = ""


class ComparisonRiskSignal(BaseModel):
    type: str
    clause: str
    detail: str
    severity: Severity


class ComparisonReport(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    comparison_id: str
    original_document: str
    modified_document: str
    original_type: str
    modified_type: str
    original_clause_count: int = Field(ge=0)
    modified_clause_count: int = Field(ge=0)
    summary: ComparisonSummary
    clause_deltas: List[ClauseDelta]
    risk_signals: List[ComparisonRiskSignal]
    notes: List[str] = Field(default_factory=list)
