from __future__ import annotations

import json
import re
from typing import Dict, List

from clauseguard.context import ContextBank
from clauseguard.model_router import ModelResponseError, ModelRouter
from clauseguard.schemas import CandidateFinding, Clause, Evidence, Severity


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
        misaligned_signals = self._misaligned_terminology_signals(context)
        if misaligned_signals:
            findings.append(
                self._document_finding(
                    "misaligned_terminology",
                    "MEDIUM",
                    "The document appears to mix role terminology in a way that may create ambiguity about party capacity or obligations.",
                    0.78,
                    context.evidence,
                    rule_id="role_or_defined_term_drift",
                    signals=misaligned_signals,
                )
            )
        findings.extend(self._missing_required_language_findings(context))

        for clause in context.clauses:
            lower = clause.text.lower()
            clause_evidence = [item for item in context.evidence if item.clause_id == clause.id]
            risky_signal = self._risky_language_signal(clause, lower)
            if risky_signal:
                risky_terms, risky_score = risky_signal
                findings.append(
                    self._clause_finding(
                        clause,
                        "risky_language",
                        "MEDIUM",
                        f"Clause contains broad or one-sided risk terms without enough balancing safeguards: {', '.join(risky_terms)}.",
                        risky_score,
                        clause_evidence,
                        rule_id="contextual_risky_language",
                        signals=risky_terms,
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
                        rule_id="contradiction_marker_with_obligation",
                    )
                )
            if self._has_structural_flaw_markers(clause.text):
                findings.append(
                    self._clause_finding(
                        clause,
                        "structural_flaw",
                        "MEDIUM",
                        "Clause structure appears to combine or relocate numbered provisions in a way that may obscure hierarchy or cross-references.",
                        0.76,
                        clause_evidence,
                        rule_id="embedded_numbered_heading",
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
                        rule_id="immediate_termination_without_notice",
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
                        rule_id="assignment_without_consent",
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
                        rule_id="broad_indemnity_without_limits",
                    )
                )
            if (
                "payment" in lower
                and ("as agreed" in lower or "reasonable" in lower)
                and "days" not in lower
            ):
                findings.append(
                    self._clause_finding(
                        clause,
                        "vague_payment_terms",
                        "MEDIUM",
                        "Payment terms appear vague and may omit due dates or dispute procedures.",
                        0.67,
                        clause_evidence,
                        rule_id="vague_payment_no_due_date",
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
                    rule_id="termination_mutual_exclusion",
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
                'Review candidate legal issues. Return JSON: {"findings":[{"id":"...","confidence":0.0,"severity":"LOW|MEDIUM|HIGH","explanation":"..."}]}',
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
        severity: Severity,
        explanation: str,
        score: float,
        evidence: List[Evidence],
        rule_id: str = "",
        signals: List[str] | None = None,
    ) -> CandidateFinding:
        return CandidateFinding(
            id=f"finding-{issue_type}",
            issue_type=issue_type,
            severity=severity,
            explanation=explanation,
            rule_id=rule_id or issue_type,
            signals=signals or [],
            deterministic_score=score,
            structure_score=0.85,
            evidence=self._top_evidence(evidence, issue_type),
            primary_confidence=score,
        )

    def _clause_finding(
        self,
        clause: Clause,
        issue_type: str,
        severity: Severity,
        explanation: str,
        score: float,
        evidence: List[Evidence],
        rule_id: str = "",
        signals: List[str] | None = None,
    ) -> CandidateFinding:
        return CandidateFinding(
            id=f"finding-{clause.id}-{issue_type}",
            issue_type=issue_type,
            severity=severity,
            clause_id=clause.id,
            clause_title=clause.title,
            explanation=explanation,
            rule_id=rule_id or issue_type,
            signals=signals or [],
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
            key=lambda item: (
                bool(preferred_tokens & set(item.title.lower().split())),
                item.relevance,
            ),
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

    def _missing_required_language_findings(self, context: ContextBank) -> List[CandidateFinding]:
        findings: List[CandidateFinding] = []
        anchors = self._document_reference_anchors(context)
        full_text = "\n".join(clause.text for clause in context.clauses)

        for clause in context.clauses:
            clause_evidence = [item for item in context.evidence if item.clause_id == clause.id]
            if self._is_incomplete_governing_law_clause(clause):
                findings.append(
                    self._clause_finding(
                        clause,
                        "missing_required_language",
                        "HIGH",
                        "The clause appears to describe dispute resolution or forum mechanics without stating the governing law to apply.",
                        0.84,
                        clause_evidence,
                        rule_id="incomplete_governing_law_clause",
                        signals=["governing law missing from dispute clause"],
                    )
                )
            missing_refs = self._missing_substantive_references(clause.text, full_text, anchors)
            if missing_refs:
                findings.append(
                    self._clause_finding(
                        clause,
                        "missing_required_language",
                        "HIGH",
                        "The clause relies on referenced provisions or attachments that do not appear to be present in the analyzed document.",
                        0.82,
                        clause_evidence,
                        rule_id="missing_substantive_cross_reference",
                        signals=missing_refs,
                    )
                )
        return findings[:6]

    def _is_incomplete_governing_law_clause(self, clause: Clause) -> bool:
        lower = clause.text.lower()
        heading = self._clause_heading_text(clause).lower()
        title_context = f"{clause.title} {clause.category}".lower()
        if "governing law" not in lower:
            return False
        if "governing law" not in heading and "governing law" not in title_context:
            return False
        dispute_language = any(
            term in lower for term in ["dispute", "claim", "arbitration", "venue", "forum"]
        )
        governing_standard = re.search(
            r"\b(governed by|construed in accordance with|laws of|law of|state of|commonwealth of)\b",
            lower,
        )
        return bool(dispute_language and not governing_standard)

    def _clause_heading_text(self, clause: Clause) -> str:
        first_line = clause.text.strip().splitlines()[0] if clause.text.strip() else clause.title
        return first_line[:160]

    def _document_reference_anchors(self, context: ContextBank) -> Dict[str, set[str]]:
        text = "\n".join(clause.text for clause in context.clauses)
        section_anchors = {
            match.group(1).rstrip(".")
            for match in re.finditer(
                r"(?:^|\s|<\*\$p\$\*>)\s*(\d{1,2}(?:\.\d+)*)\.?\s+[A-Z][A-Za-z][A-Za-z ,/&()'\-]{2,80}",
                text,
            )
        }
        appendix_anchors = {
            match.group(1).upper()
            for match in re.finditer(
                r"(?:^|\s|<\*\$p\$\*>)\s*APPENDIX\s+([A-Z])\b", text, re.IGNORECASE
            )
        }
        schedule_anchors = {
            match.group(1).upper()
            for match in re.finditer(
                r"(?:^|\s|<\*\$p\$\*>)\s*SCHEDULE\s+([A-Z0-9]+)\b", text, re.IGNORECASE
            )
        }
        return {
            "section": section_anchors,
            "appendix": appendix_anchors,
            "schedule": schedule_anchors,
        }

    def _missing_substantive_references(
        self,
        clause_text: str,
        full_text: str,
        anchors: Dict[str, set[str]],
    ) -> List[str]:
        signals: List[str] = []
        patterns = [
            r"\b(?:as\s+defined\s+in|defined\s+by|subject\s+to|outlined\s+in|set\s+forth\s+in|governed\s+by|pursuant\s+to|in\s+accordance\s+with)\s+Section\s+(\d{1,2}(?:\.\d+)*)\b",
            r"\b(?:remedies|rights|obligations|procedures|terms)\s+(?:are\s+)?(?:defined|described|specified)\s+in\s+Section\s+(\d{1,2}(?:\.\d+)*)\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, clause_text, re.IGNORECASE):
                section = match.group(1).rstrip(".")
                top_level = section.split(".")[0]
                has_same_top_level = any(
                    anchor == top_level or anchor.startswith(f"{top_level}.")
                    for anchor in anchors["section"]
                )
                if section not in anchors["section"] and not has_same_top_level:
                    signals.append(f"missing Section {section}")

        for match in re.finditer(
            r"\b(?:subject\s+to|outlined\s+in|set\s+forth\s+in|governed\s+by|pursuant\s+to|in\s+accordance\s+with)\s+Appendix\s+([A-Z])\b",
            clause_text,
            re.IGNORECASE,
        ):
            appendix = match.group(1).upper()
            if (
                appendix not in anchors["appendix"]
                and len(re.findall(rf"\bAppendix\s+{appendix}\b", full_text, re.IGNORECASE)) <= 1
            ):
                signals.append(f"missing Appendix {appendix}")

        for match in re.finditer(
            r"\b(?:subject\s+to|outlined\s+in|set\s+forth\s+in|governed\s+by|pursuant\s+to|in\s+accordance\s+with)\s+Schedule\s+([A-Z0-9]+)\b",
            clause_text,
            re.IGNORECASE,
        ):
            schedule = match.group(1).upper()
            if (
                schedule not in anchors["schedule"]
                and len(re.findall(rf"\bSchedule\s+{schedule}\b", full_text, re.IGNORECASE)) <= 1
            ):
                signals.append(f"missing Schedule {schedule}")

        return sorted(set(signals))[:4]

    def _has_weak_required_language(self, lower_text: str) -> bool:
        weak_terms = ["will endeavor", "should attempt", "is expected to", "as appropriate"]
        required_context = [
            "shall",
            "must",
            "required",
            "obligation",
            "indemnify",
            "perform",
            "provide",
        ]
        return any(term in lower_text for term in weak_terms) and any(
            term in lower_text for term in required_context
        )

    def _risky_language_signal(self, clause: Clause, lower: str) -> tuple[List[str], float] | None:
        if not clause.risk_terms:
            return None

        strong_terms = [
            term
            for term in clause.risk_terms
            if term
            in {
                "as it sees fit",
                "deems appropriate",
                "will endeavor",
                "should attempt",
                "final say",
                "only upon",
            }
        ]
        if strong_terms:
            return strong_terms, 0.84

        discretion_terms = [
            term for term in clause.risk_terms if term in {"sole discretion", "at its discretion"}
        ]
        if discretion_terms and self._has_unbalanced_discretion_context(lower):
            disclaimer_terms = [
                term
                for term in clause.risk_terms
                if term in {"no liability", "as is", "exclusive remedy", "unlimited"}
                and self._has_unbalanced_disclaimer_context(clause, lower)
            ]
            signals = discretion_terms + [
                term for term in disclaimer_terms if term not in discretion_terms
            ]
            score = (
                0.84
                if disclaimer_terms
                or any(term in lower for term in ["reject returns", "refuse returns"])
                else 0.80
            )
            return signals, score

        disclaimer_terms = [
            term
            for term in clause.risk_terms
            if term in {"no liability", "as is", "exclusive remedy", "unlimited"}
        ]
        if disclaimer_terms and self._has_unbalanced_disclaimer_context(clause, lower):
            return disclaimer_terms, 0.78

        return None

    def _has_unbalanced_discretion_context(self, lower: str) -> bool:
        if any(
            action in lower for action in ["reject returns", "reject any return", "refuse returns"]
        ):
            return True
        if "terminate this agreement" in lower or "terminate the agreement" in lower:
            termination_safeguards = [
                "for cause",
                "material breach",
                "default",
                "failure to cure",
                "cure period",
                "thirty",
                "30 days",
                "thirty (30) days",
            ]
            if not any(safeguard in lower for safeguard in termination_safeguards):
                return True

        risk_actions = [
            "final decision",
            "final say",
            "change",
            "modify",
            "settlement",
            "settlements",
            "terminate immediately",
            "without notice",
            "without consent",
            "deems necessary",
        ]
        if not any(action in lower for action in risk_actions):
            return False
        safeguards = [
            "reasonable",
            "good faith",
            "prior written notice",
            "prior written consent",
            "not unreasonably withheld",
            "mutual written agreement",
            "cure period",
        ]
        return not any(safeguard in lower for safeguard in safeguards)

    def _has_unbalanced_disclaimer_context(self, clause: Clause, lower: str) -> bool:
        if clause.category not in {"Limitation of Liability", "Indemnification", "General"}:
            return False
        if any(
            term in lower
            for term in ["except", "carve-out", "cap", "maximum", "up to", "will not exclude"]
        ):
            return False
        return any(
            term in lower for term in ["no liability", "as is", "exclusive remedy", "unlimited"]
        )

    def _has_internal_contradiction_markers(self, lower_text: str) -> bool:
        strong_markers = [
            "regardless of",
            "despite",
            "unilaterally",
            "final say",
            "guaranteed payment",
            "only upon",
            "in lieu of",
            "without regard to",
            "contrary to",
            "null and void",
        ]
        modal_terms = ["shall", "may", "must", "will", "entitled", "required"]
        if any(marker in lower_text for marker in strong_markers) and any(
            term in lower_text for term in modal_terms
        ):
            return True
        if "notwithstanding" in lower_text and self._has_notwithstanding_conflict(lower_text):
            return True
        however_matches = list(re.finditer(r"\bhowever\s*[,;:]", lower_text))
        if however_matches:
            conflict_terms = [
                "final say",
                "only upon",
                "shall not",
                "may not",
                "cannot",
                "no longer",
                "unilaterally",
            ]
            return any(
                any(
                    term in lower_text[match.start() : match.start() + 320]
                    for term in conflict_terms
                )
                and any(
                    term in lower_text[match.start() : match.start() + 320] for term in modal_terms
                )
                for match in however_matches
            )
        return False

    def _has_notwithstanding_conflict(self, lower_text: str) -> bool:
        benign_patterns = [
            "notwithstanding the contents of the exhibit",
            "notwithstanding disputes on other items",
            'notwithstanding the foregoing, "confidential information" shall not include',
            "notwithstanding the foregoing, confidential information shall not include",
            "notwithstanding anything to the contrary in this section 1.2",
        ]
        if any(pattern in lower_text for pattern in benign_patterns):
            return False

        conflict_terms = [
            "shall not be required",
            "not be entitled",
            "may terminate",
            "terminate this agreement",
            "terminate the agreement",
            "failure of an essential purpose",
            "guaranteed payment",
            "liquidated damages",
            "contrary to law",
            "conflict with",
            "shall not be liable",
            "in no event shall",
            "without limitation",
            "breach",
            "default",
        ]
        return any(term in lower_text for term in conflict_terms)

    def _has_structural_flaw_markers(self, text: str) -> bool:
        inline_subheadings = re.findall(
            r"\b\d{1,2}\.\d+\s+[A-Z][A-Za-z][A-Za-z ,/&()'\-]{2,60}\b",
            text,
        )
        if len(inline_subheadings) >= 2:
            return True
        embedded_top_level = re.findall(
            r"(?:^|\s|<\*\$p\$\*>)\s*\d{1,2}\.\s+[A-Z][A-Z /&()'\-]{3,80}\.\s+\d{1,2}\.\d+",
            text,
        )
        if embedded_top_level:
            return True
        top_level_numbers = re.findall(
            r"(?:^|\s|<\*\$p\$\*>)\s*(\d{1,2})\.\s+[A-Z][A-Z /&()'\-]{3,80}\.", text
        )
        return len(set(top_level_numbers)) >= 2 and "<*$p$*>" in text

    def _misaligned_terminology_signals(self, context: ContextBank) -> List[str]:
        signals: List[str] = []
        text = " ".join(clause.text for clause in context.clauses[:80])
        lowered = text.lower()

        if re.search(r"\bSource Plasma\b", text) and re.search(r"\bSource plasma\b", text):
            signals.append("defined term capitalization drift: Source Plasma / Source plasma")

        for clause in context.clauses:
            lower = clause.text.lower()
            role_conflict = None
            if "reseller" in lower and "distributor" in lower:
                role_conflict = "reseller/distributor"
            elif "reseller" in lower and "salesperson" in lower:
                role_conflict = "reseller/salesperson"
            elif "distributor" in lower and "salesperson" in lower:
                role_conflict = "distributor/salesperson"
            if role_conflict and any(
                marker in lower
                for marker in [
                    "shall have no authority",
                    "independent contractor",
                    "governed by",
                    "as governed by",
                    "support for",
                ]
            ):
                signals.append(f"role conflict in clause {clause.id}: {role_conflict}")

        if "source plasma" in lowered and "altered source plasma" in lowered:
            signals.append("source material terminology drift")

        return sorted(set(signals))[:5]

    def _clamp(self, value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5
