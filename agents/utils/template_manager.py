from __future__ import annotations

from typing import Dict, List


class TemplateManager:
    """Small fallback template manager for the legacy clause rewriter."""

    def __init__(self):
        self.templates: List[Dict[str, str]] = [
            {
                "category": "Termination",
                "text": "Either party may terminate for material breach after written notice and a reasonable cure period.",
            },
            {
                "category": "Confidentiality",
                "text": "Each party shall protect confidential information using reasonable safeguards and permitted-use limits.",
            },
            {
                "category": "Indemnification",
                "text": "Indemnity applies to specified third-party claims, subject to notice, defense cooperation, and exclusions.",
            },
        ]

    def find_similar_templates(self, clause_text: str, limit: int = 3) -> List[Dict[str, str]]:
        lower = clause_text.lower()
        scored = []
        for template in self.templates:
            score = sum(1 for word in template["category"].lower().split() if word in lower)
            score += sum(1 for word in template["text"].lower().split() if word in lower)
            scored.append((score, template))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [template for score, template in scored[:limit] if score > 0]
