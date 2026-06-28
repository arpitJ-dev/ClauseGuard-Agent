from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable, List

from legal_lm.agents.compliance import ComplianceCheckerAgent
from legal_lm.agents.preprocessor import PreprocessorAgent
from legal_lm.agents.rewriter import ClauseRewriterAgent
from legal_lm.agents.verifier import VerifierAgent
from legal_lm.config import AppConfig
from legal_lm.context import ContextBank
from legal_lm.document import DocumentLoader
from legal_lm.model_router import ModelRouter
from legal_lm.postprocessor import Postprocessor
from legal_lm.rag import KnowledgeAgent
from legal_lm.schemas import AnalysisReport, CandidateFinding, Finding
from legal_lm.scoring import WeightedScorer


class LegalAnalysisPipeline:
    def __init__(self, config: AppConfig):
        self.config = config
        self.router = ModelRouter(config)
        self.loader = DocumentLoader()
        self.preprocessor = PreprocessorAgent(self.router)
        self.knowledge = KnowledgeAgent(self.router)
        self.compliance = ComplianceCheckerAgent(self.router)
        self.verifier = VerifierAgent(self.router)
        self.scorer = WeightedScorer()
        self.rewriter = ClauseRewriterAgent(self.router)
        self.postprocessor = Postprocessor()

    @classmethod
    def from_env(cls, mock_models: bool = False) -> "LegalAnalysisPipeline":
        return cls(AppConfig.from_env(mock_models=mock_models))

    def analyze(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        output_formats: Iterable[str] = ("json", "markdown"),
        include_rewrites: bool = True,
    ) -> AnalysisReport:
        context = ContextBank(document_id=str(uuid.uuid4()))
        document = self.loader.load(file_path)
        document_type, clauses, entities = self.preprocessor.process(document)

        context.add_document(document, document_type)
        context.add_clauses(clauses)
        context.add_entities(entities)
        context.add_evidence(self.knowledge.retrieve_for_clauses(clauses))

        candidates = self.compliance.analyze(context)
        verified = self.verifier.verify(candidates, context)
        findings = self._score_findings(verified)
        context.add_findings(findings)
        if include_rewrites:
            context.add_rewrites(self.rewriter.rewrite(context, findings))

        report = self.postprocessor.build_report(context)
        if output_dir:
            self.postprocessor.write_outputs(report, output_dir, output_formats)
        return report

    def _score_findings(self, candidates: List[CandidateFinding]) -> List[Finding]:
        findings: List[Finding] = []
        for candidate in candidates:
            rag_score = max((evidence.relevance for evidence in candidate.evidence), default=0.35)
            scores = self.scorer.score(
                deterministic_rules=candidate.deterministic_score,
                rag_evidence=rag_score,
                primary_reasoning=candidate.primary_confidence,
                verifier_agreement=candidate.verifier_confidence,
                clause_structure=candidate.structure_score,
            )
            findings.append(
                Finding(
                    id=candidate.id,
                    issue_type=candidate.issue_type,
                    severity=candidate.severity,
                    clause_id=candidate.clause_id,
                    clause_title=candidate.clause_title,
                    explanation=candidate.explanation,
                    evidence=candidate.evidence,
                    component_scores=scores,
                    accepted=self.scorer.is_accepted(scores, candidate.issue_type),
                    model_confidence=candidate.primary_confidence,
                    verifier_confidence=candidate.verifier_confidence,
                    verifier_rationale=candidate.verifier_rationale,
                )
            )
        return findings
