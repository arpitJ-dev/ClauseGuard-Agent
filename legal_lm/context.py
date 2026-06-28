from __future__ import annotations

from typing import List, Optional

from legal_lm.schemas import Clause, Evidence, Finding, LegalEntity, LoadedDocument, Rewrite


class ContextBank:
    """Single-document context store shared by the v1 agents."""

    def __init__(self, document_id: str):
        self.document_id = document_id
        self.document: Optional[LoadedDocument] = None
        self.document_type: str = "Unknown"
        self.clauses: List[Clause] = []
        self.entities: List[LegalEntity] = []
        self.evidence: List[Evidence] = []
        self.findings: List[Finding] = []
        self.rewrites: List[Rewrite] = []

    def add_document(self, document: LoadedDocument, document_type: str = "Unknown") -> None:
        self.document = document
        self.document_type = document_type

    def add_clauses(self, clauses: List[Clause]) -> None:
        self.clauses = clauses

    def add_entities(self, entities: List[LegalEntity]) -> None:
        self.entities = entities

    def add_evidence(self, evidence: List[Evidence]) -> None:
        self.evidence = evidence

    def add_findings(self, findings: List[Finding]) -> None:
        self.findings = findings

    def add_rewrites(self, rewrites: List[Rewrite]) -> None:
        self.rewrites = rewrites

    def get_clause(self, clause_id: str | None) -> Optional[Clause]:
        if not clause_id:
            return None
        return next((clause for clause in self.clauses if clause.id == clause_id), None)
