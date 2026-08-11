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
from clauseguard.events import ProgressCallback, notify
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
        run_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AnalysisReport:
        formats = tuple(output_formats)
        context = ContextBank(document_id=run_id or str(uuid.uuid4()))

        notify(progress_callback, "loading", "started", 5, "Loading document")
        document = self.loader.load(file_path)
        notify(
            progress_callback,
            "loading",
            "completed",
            10,
            "Document loaded",
            file_type=document.file_type,
            title=document.title,
        )

        notify(progress_callback, "extracting", "started", 15, "Extracting contract structure")
        document_type, clauses, entities = self.preprocessor.process(document)
        notify(
            progress_callback,
            "extracting",
            "completed",
            25,
            "Contract structure extracted",
            document_type=document_type,
            clause_count=len(clauses),
            entity_count=len(entities),
        )

        context.add_document(document, document_type)
        context.add_clauses(clauses)
        context.add_entities(entities)

        notify(progress_callback, "retrieving", "started", 30, "Retrieving review evidence")
        context.add_evidence(self.knowledge.retrieve_for_clauses(clauses))
        notify(
            progress_callback,
            "retrieving",
            "completed",
            40,
            "Review evidence retrieved",
            evidence_count=len(context.evidence),
        )

        notify(progress_callback, "checking", "started", 45, "Checking contract risks")
        candidates = self.compliance.analyze(context)
        context.merge_evidence(self.knowledge.retrieve_for_findings(candidates, clauses))
        notify(
            progress_callback,
            "checking",
            "completed",
            57,
            "Candidate findings generated",
            candidate_count=len(candidates),
        )

        notify(progress_callback, "verifying", "started", 60, "Verifying candidate findings")
        verified = self.verifier.verify(candidates, context)
        notify(
            progress_callback,
            "verifying",
            "completed",
            70,
            "Candidate findings verified",
            candidate_count=len(verified),
        )

        notify(progress_callback, "scoring", "started", 73, "Scoring evidence")
        findings = self._score_findings(verified)
        context.add_findings(findings)
        notify(
            progress_callback,
            "scoring",
            "completed",
            80,
            "Evidence scoring completed",
            finding_count=len(findings),
            accepted_count=sum(1 for finding in findings if finding.accepted),
        )

        notify(progress_callback, "rewriting", "started", 83, "Drafting clause rewrites")
        if include_rewrites:
            context.add_rewrites(self.rewriter.rewrite(context, findings))
        notify(
            progress_callback,
            "rewriting",
            "completed",
            90,
            "Clause rewrites completed",
            rewrite_count=len(context.rewrites),
        )

        notify(progress_callback, "reporting", "started", 93, "Building analysis report")
        report = self.postprocessor.build_report(context)
        if output_dir:
            self.postprocessor.write_outputs(report, output_dir, formats)
        notify(
            progress_callback,
            "reporting",
            "completed",
            98,
            "Analysis report built",
            output_dir=str(output_dir) if output_dir else None,
            output_formats=list(formats),
        )
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
