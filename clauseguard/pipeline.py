from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable, List

from clauseguard.agents.compliance import ComplianceCheckerAgent
from clauseguard.agents.preprocessor import PreprocessorAgent
from clauseguard.agents.rewriter import ClauseRewriterAgent
from clauseguard.agents.verifier import VerifierAgent
from clauseguard.config import AppConfig
from clauseguard.context import ContextBank
from clauseguard.document import DocumentLoader
from clauseguard.model_router import ModelRouter
from clauseguard.postprocessor import Postprocessor
from clauseguard.rag import KnowledgeAgent
from clauseguard.schemas import AnalysisReport, CandidateFinding, Finding
from clauseguard.scoring import WeightedScorer


class ClauseGuardPipeline:
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
    def from_env(cls, mock_models: bool = False) -> "ClauseGuardPipeline":
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
        context.merge_evidence(self.knowledge.retrieve_for_findings(candidates, clauses))
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
                    rule_id=candidate.rule_id,
                    signals=candidate.signals,
                    evidence=candidate.evidence,
                    component_scores=scores,
                    accepted=self.scorer.is_accepted(scores, candidate.issue_type),
                    acceptance_threshold=self.scorer.threshold_for(candidate.issue_type),
                    model_confidence=candidate.primary_confidence,
                    verifier_confidence=candidate.verifier_confidence,
                    verifier_status=candidate.verifier_status,
                    verifier_rationale=candidate.verifier_rationale,
                )
            )
        return findings
