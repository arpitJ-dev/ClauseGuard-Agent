from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    clause_id: Optional[str] = None
    clause_title: Optional[str] = None
    explanation: str
    deterministic_score: float = Field(ge=0.0, le=1.0)
    structure_score: float = Field(ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list)
    primary_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verifier_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verifier_rationale: str = ""


class Finding(BaseModel):
    id: str
    issue_type: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    clause_id: Optional[str] = None
    clause_title: Optional[str] = None
    explanation: str
    evidence: List[Evidence] = Field(default_factory=list)
    component_scores: ComponentScores
    accepted: bool
    model_confidence: float = Field(ge=0.0, le=1.0)
    verifier_confidence: float = Field(ge=0.0, le=1.0)
    verifier_rationale: str = ""
    suggested_rewrite: Optional[str] = None


class Rewrite(BaseModel):
    clause_id: str
    original_text: str
    rewritten_text: str
    rationale: str


class AnalysisReport(BaseModel):
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
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    limitations: List[str] = Field(
        default_factory=lambda: [
            "This system is a legal analysis assistant and not a lawyer replacement.",
            "Findings require review by a qualified legal professional.",
            "External model APIs may throttle or fail when quota is exhausted.",
        ]
    )
