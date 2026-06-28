from __future__ import annotations

import json
import re
from typing import Dict, List

from legal_lm.context import ContextBank
from legal_lm.model_router import ModelResponseError, ModelRouter
from legal_lm.schemas import CandidateFinding, Clause, Evidence


class ComplianceCheckerAgent:
    def __init__(self, router: ModelRouter):
        self.router = router

    def analyze(self, context: ContextBank) -> List[CandidateFinding]:
        candidates = self._deterministic_findings(context)
        if not candidates:
            return []

        confidence_updates = self._primary_review(candidates)
        for candidate in candidates:
            update = confidence_updates.get(candidate.id, {})
            if "confidence" in update:
                candidate.primary_confidence = self._clamp(update["confidence"])
            if update.get("explanation"):
                candidate.explanation = str(update["explanation"])[:1200]
            if update.get("severity") in {"LOW", "MEDIUM", "HIGH"}:
                candidate.severity = update["severity"]
        return candidates

    def _deterministic_findings(self, context: ContextBank) -> List[CandidateFinding]:
        findings: List[CandidateFinding] = []
        categories = {clause.category for clause in context.clauses}

        if "Governing Law" not in categories:
            findings.append(
                self._document_finding(
                    "missing_governing_law",
                    "HIGH",
                    "No governing law or venue clause was detected, making dispute forum and applicable law unclear.",
                    0.85,
                    context.evidence,
                )
            )
        if "Termination" not in categories:
            findings.append(
                self._document_finding(
                    "missing_termination",
                    "MEDIUM",
                    "No termination clause was detected, so exit rights, notice, and cure periods may be undefined.",
                    0.72,
                    context.evidence,
                )
            )
        if "Confidentiality" not in categories and context.document_type.lower() in {
            "services agreement",
            "supply agreement",
            "affiliate agreement",
            "consulting agreement",
            "commercial agreement",
        }:
            findings.append(
                self._document_finding(
                    "missing_confidentiality",
                    "MEDIUM",
                    "No confidentiality clause was detected for a commercial relationship where sensitive information may be exchanged.",
                    0.68,
                    context.evidence,
                )
            )
        if self._has_misaligned_terminology(context):
            findings.append(
                self._document_finding(
                    "misaligned_terminology",
                    "MEDIUM",
                    "The document appears to mix role terminology in a way that may create ambiguity about party capacity or obligations.",
                    0.70,
                    context.evidence,
                )
            )

        for clause in context.clauses:
            lower = clause.text.lower()
            clause_evidence = [item for item in context.evidence if item.clause_id == clause.id]
            if clause.risk_terms:
                findings.append(
                    self._clause_finding(
                        clause,
                        "risky_language",
                        "MEDIUM",
                        f"Clause contains broad or one-sided risk terms: {', '.join(clause.risk_terms)}.",
                        0.70,
                        clause_evidence,
                    )
                )
            if self._has_internal_contradiction_markers(lower):
                findings.append(
                    self._clause_finding(
                        clause,
                        "internal_contradiction",
                        "HIGH",
                        "Clause contains contrast or override language that may conflict with nearby obligations or exceptions.",
                        0.76,
                        clause_evidence,
                    )
                )
            if self._has_structural_flaw_markers(clause.text):
                findings.append(
                    self._clause_finding(
                        clause,
                        "structural_flaw",
                        "MEDIUM",
                        "Clause structure appears to combine or relocate numbered provisions in a way that may obscure hierarchy or cross-references.",
                        0.68,
                        clause_evidence,
                    )
                )
            if "terminate" in lower and "immediately" in lower and "notice" not in lower:
                findings.append(
                    self._clause_finding(
                        clause,
                        "termination_without_notice",
                        "HIGH",
                        "Termination appears immediate without a clear notice or cure period.",
                        0.82,
                        clause_evidence,
                    )
                )
            if "assign" in lower and "without consent" in lower:
                findings.append(
                    self._clause_finding(
                        clause,
                        "assignment_without_consent",
                        "MEDIUM",
                        "Assignment may be allowed without consent, which can unexpectedly transfer obligations.",
                        0.72,
                        clause_evidence,
                    )
                )
            if "indemn" in lower and ("any and all" in lower or "without limitation" in lower):
                findings.append(
                    self._clause_finding(
                        clause,
                        "uncapped_indemnity",
                        "HIGH",
                        "Indemnity language appears broad and may lack procedural limits or liability caps.",
                        0.84,
                        clause_evidence,
                    )
                )
            if "payment" in lower and ("as agreed" in lower or "reasonable" in lower) and "days" not in lower:
                findings.append(
                    self._clause_finding(
                        clause,
                        "vague_payment_terms",
                        "MEDIUM",
                        "Payment terms appear vague and may omit due dates or dispute procedures.",
                        0.67,
                        clause_evidence,
                    )
                )

        contradictory_terms = self._find_termination_contradiction(context.clauses)
        if contradictory_terms:
            clause = contradictory_terms
            findings.append(
                self._clause_finding(
                    clause,
                    "internal_contradiction",
                    "HIGH",
                    "Termination language appears internally inconsistent across the document.",
                    0.80,
                    [item for item in context.evidence if item.clause_id == clause.id],
                )
            )

        return findings[:40]

    def _primary_review(self, candidates: List[CandidateFinding]) -> Dict[str, Dict]:
        payload = [
            {
                "id": item.id,
                "issue_type": item.issue_type,
                "severity": item.severity,
                "explanation": item.explanation,
                "evidence_titles": [evidence.title for evidence in item.evidence[:3]],
            }
            for item in candidates
        ]
        try:
            response = self.router.generate_json(
                "reasoning",
                "Review candidate legal issues. Return JSON: {\"findings\":[{\"id\":\"...\",\"confidence\":0.0,\"severity\":\"LOW|MEDIUM|HIGH\",\"explanation\":\"...\"}]}",
                json.dumps(payload),
            )
        except ModelResponseError:
            return {}
        updates = {}
        for raw in response.get("findings", []):
            if isinstance(raw, dict) and raw.get("id"):
                updates[str(raw["id"])] = raw
        return updates

    def _document_finding(
        self,
        issue_type: str,
        severity: str,
        explanation: str,
        score: float,
        evidence: List[Evidence],
    ) -> CandidateFinding:
        return CandidateFinding(
            id=f"finding-{issue_type}",
            issue_type=issue_type,
            severity=severity,
            explanation=explanation,
            deterministic_score=score,
            structure_score=0.85,
            evidence=self._top_evidence(evidence, issue_type),
            primary_confidence=score,
        )

    def _clause_finding(
        self,
        clause: Clause,
        issue_type: str,
        severity: str,
        explanation: str,
        score: float,
        evidence: List[Evidence],
    ) -> CandidateFinding:
        return CandidateFinding(
            id=f"finding-{clause.id}-{issue_type}",
            issue_type=issue_type,
            severity=severity,
            clause_id=clause.id,
            clause_title=clause.title,
            explanation=explanation,
            deterministic_score=score,
            structure_score=0.70 if clause.category == "General" else 0.82,
            evidence=self._top_evidence(evidence, issue_type),
            primary_confidence=score,
        )

    def _top_evidence(self, evidence: List[Evidence], issue_type: str) -> List[Evidence]:
        preferred_tokens = {
            token
            for token in issue_type.replace("missing_", "").split("_")
            if token not in {"risky", "language", "uncapped", "terms"}
        }
        if not preferred_tokens:
            return evidence[:3]
        ranked = sorted(
            evidence,
            key=lambda item: (bool(preferred_tokens & set(item.title.lower().split())), item.relevance),
            reverse=True,
        )
        return ranked[:3]

    def _find_termination_contradiction(self, clauses: List[Clause]) -> Clause | None:
        termination_clauses = [clause for clause in clauses if clause.category == "Termination"]
        for clause in termination_clauses:
            lower = clause.text.lower()
            if "may terminate at any time" in lower and "may not terminate" in lower:
                return clause
        return None

    def _has_internal_contradiction_markers(self, lower_text: str) -> bool:
        markers = [
            "however",
            "notwithstanding",
            "regardless of",
            "despite",
            "unilaterally",
            "final say",
            "guaranteed payment",
            "only upon",
            "in lieu of",
            "without regard to",
        ]
        modal_terms = ["shall", "may", "must", "will", "entitled", "required"]
        return any(marker in lower_text for marker in markers) and any(term in lower_text for term in modal_terms)

    def _has_structural_flaw_markers(self, text: str) -> bool:
        section_refs = re.findall(r"\b\d{1,2}\.\d+\b", text)
        if len(section_refs) >= 3:
            return True
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        return bool(re.search(r"^\s*\d{1,2}\.\s+.+\b\d{1,2}\.\d+\b", first_line))

    def _has_misaligned_terminology(self, context: ContextBank) -> bool:
        text = " ".join(clause.text.lower() for clause in context.clauses[:80])
        role_pairs = [
            ("reseller", "distributor"),
            ("reseller", "salesperson"),
            ("distributor", "salesperson"),
            ("consultant", "employee"),
            ("manufacturer", "customer"),
        ]
        return any(left in text and right in text for left, right in role_pairs)

    def _clamp(self, value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5
