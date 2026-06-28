from __future__ import annotations

from typing import Dict

from legal_lm.schemas import ComponentScores


WEIGHTS: Dict[str, float] = {
    "deterministic_rules": 0.30,
    "rag_evidence": 0.25,
    "primary_reasoning": 0.20,
    "verifier_agreement": 0.15,
    "clause_structure": 0.10,
}

ISSUE_ACCEPTANCE_THRESHOLDS: Dict[str, float] = {
    "structural_flaw": 0.60,
}


class WeightedScorer:
    def __init__(self, acceptance_threshold: float = 0.55):
        self.acceptance_threshold = acceptance_threshold

    def score(
        self,
        deterministic_rules: float,
        rag_evidence: float,
        primary_reasoning: float,
        verifier_agreement: float,
        clause_structure: float,
    ) -> ComponentScores:
        values = {
            "deterministic_rules": self._clamp(deterministic_rules),
            "rag_evidence": self._clamp(rag_evidence),
            "primary_reasoning": self._clamp(primary_reasoning),
            "verifier_agreement": self._clamp(verifier_agreement),
            "clause_structure": self._clamp(clause_structure),
        }
        final = sum(values[name] * weight for name, weight in WEIGHTS.items())
        return ComponentScores(**values, final=round(final, 4), weights=WEIGHTS)

    def is_accepted(self, scores: ComponentScores, issue_type: str | None = None) -> bool:
        threshold = ISSUE_ACCEPTANCE_THRESHOLDS.get(issue_type or "", self.acceptance_threshold)
        return scores.final >= threshold

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, float(value)))
