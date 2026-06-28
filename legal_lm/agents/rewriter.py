from __future__ import annotations

from typing import List

from legal_lm.context import ContextBank
from legal_lm.model_router import ModelRouter
from legal_lm.schemas import Finding, Rewrite


class ClauseRewriterAgent:
    def __init__(self, router: ModelRouter):
        self.router = router

    def rewrite(self, context: ContextBank, findings: List[Finding]) -> List[Rewrite]:
        rewrites: List[Rewrite] = []
        for finding in findings:
            if not finding.accepted or not finding.clause_id:
                continue
            clause = context.get_clause(finding.clause_id)
            if not clause:
                continue
            fallback = self._fallback_rewrite(clause.text, finding.issue_type)
            model_text = self.router.generate_text(
                "rewrite",
                "Rewrite the clause to reduce the flagged legal risk. Return only the revised clause text.",
                f"Issue: {finding.issue_type}\nExplanation: {finding.explanation}\nClause:\n{clause.text}",
            )
            revised = model_text.strip() if len(model_text.strip()) >= 40 else fallback
            rewrites.append(
                Rewrite(
                    clause_id=clause.id,
                    original_text=clause.text,
                    rewritten_text=revised,
                    rationale=f"Addresses {finding.issue_type} while preserving the clause's commercial intent.",
                )
            )
            finding.suggested_rewrite = revised
        return rewrites

    def _fallback_rewrite(self, text: str, issue_type: str) -> str:
        if issue_type == "termination_without_notice":
            return (
                f"{text}\n\nRevised safeguard: Either party may terminate only after written notice and a reasonable cure period, "
                "except for uncured material breach, insolvency, unlawful conduct, or other expressly stated immediate-termination triggers."
            )
        if issue_type == "assignment_without_consent":
            return (
                f"{text}\n\nRevised safeguard: Neither party may assign this agreement without prior written consent, "
                "except to an affiliate or successor in connection with a merger, reorganization, or sale of substantially all assets."
            )
        if issue_type == "uncapped_indemnity":
            return (
                f"{text}\n\nRevised safeguard: Indemnification is limited to third-party claims caused by breach, negligence, "
                "willful misconduct, or legal violation, subject to prompt notice, defense control, cooperation, and agreed liability caps."
            )
        return (
            f"{text}\n\nRevised safeguard: The parties will apply objective standards, written notice, reasonable cooperation, "
            "and mutually balanced obligations when performing this clause."
        )
