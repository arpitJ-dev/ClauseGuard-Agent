from __future__ import annotations

import json
from typing import Dict, List

from legal_lm.context import ContextBank
from legal_lm.model_router import ModelResponseError, ModelRouter
from legal_lm.schemas import CandidateFinding


class VerifierAgent:
    def __init__(self, router: ModelRouter):
        self.router = router

    def verify(self, findings: List[CandidateFinding], context: ContextBank | None = None) -> List[CandidateFinding]:
        if not findings:
            return []
        document_context = self._document_context(context)
        payload = {
            "document_context": document_context,
            "findings": [
                {
                    "id": finding.id,
                    "issue_type": finding.issue_type,
                    "severity": finding.severity,
                    "explanation": finding.explanation[:700],
                    "evidence": [
                        {"title": evidence.title, "text": evidence.text[:300], "relevance": evidence.relevance}
                        for evidence in finding.evidence[:2]
                    ],
                    "affected_clause": self._affected_clause(context, finding),
                }
                for finding in findings[:25]
            ],
        }
        try:
            response = self.router.generate_json(
                "verifier",
                (
                    "You are an independent legal QA verifier. Verify whether each finding is supported by "
                    "the detected clause categories, affected clause text, and local evidence. The user payload contains "
                    "document_context plus a findings array. For missing-clause findings, use "
                    "document_context.detected_clause_categories to assess whether the clause appears absent. "
                    "Return JSON: {\"verifications\":[{\"id\":\"...\",\"agreement\":0.0,\"confidence\":0.0,\"rationale\":\"...\"}]}"
                ),
                json.dumps(payload),
            )
        except ModelResponseError:
            response = {"verifications": []}

        updates: Dict[str, Dict] = {}
        for raw in response.get("verifications", []):
            if isinstance(raw, dict) and raw.get("id"):
                updates[str(raw["id"])] = raw

        for finding in findings:
            update = updates.get(finding.id)
            if update:
                agreement = self._clamp(update.get("agreement", update.get("confidence", 0.5)))
                confidence = self._clamp(update.get("confidence", agreement))
                finding.verifier_confidence = round((agreement + confidence) / 2.0, 4)
                finding.verifier_rationale = str(update.get("rationale", ""))[:1000]
            else:
                finding.verifier_confidence = max(0.55, finding.primary_confidence - 0.10)
                finding.verifier_rationale = "Verifier fallback used because no structured verifier response was returned."
        return findings

    def _document_context(self, context: ContextBank | None) -> Dict:
        if context is None:
            return {}
        return {
            "document_type": context.document_type,
            "detected_clause_categories": sorted({clause.category for clause in context.clauses}),
            "detected_clause_titles": [clause.title[:80] for clause in context.clauses[:30]],
        }

    def _affected_clause(self, context: ContextBank | None, finding: CandidateFinding) -> Dict | None:
        if context is None or not finding.clause_id:
            return None
        clause = context.get_clause(finding.clause_id)
        if not clause:
            return None
        return {
            "id": clause.id,
            "title": clause.title,
            "category": clause.category,
            "text": clause.text[:800],
        }

    def _clamp(self, value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5
