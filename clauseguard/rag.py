from __future__ import annotations

import math
from typing import Dict, Iterable, List, Tuple

from clauseguard.model_router import ModelRouter
from clauseguard.schemas import CandidateFinding, Clause, Evidence

REFERENCE_CORPUS: List[Dict[str, str]] = [
    {
        "id": "ref-governing-law",
        "source": "local_reference",
        "title": "Governing Law Checklist",
        "text": "Commercial agreements should identify governing law and venue so disputes have a predictable forum.",
    },
    {
        "id": "ref-confidentiality",
        "source": "local_reference",
        "title": "Confidentiality Checklist",
        "text": "Confidentiality clauses should define confidential information, exclusions, permitted disclosures, duration, and remedies.",
    },
    {
        "id": "ref-termination",
        "source": "local_reference",
        "title": "Termination Checklist",
        "text": "Termination clauses should state notice periods, cure periods, immediate termination triggers, and post-termination duties.",
    },
    {
        "id": "ref-indemnity",
        "source": "local_reference",
        "title": "Indemnity Checklist",
        "text": "Indemnity clauses should specify covered claims, procedures, exclusions, control of defense, and liability caps where appropriate.",
    },
    {
        "id": "ref-payment",
        "source": "local_reference",
        "title": "Payment Checklist",
        "text": "Payment clauses should specify fees, invoices, due dates, late fees, taxes, audit rights, and dispute procedures.",
    },
    {
        "id": "ref-assignment",
        "source": "local_reference",
        "title": "Assignment Checklist",
        "text": "Assignment clauses usually require prior written consent except for mergers, affiliates, or sale of substantially all assets.",
    },
    {
        "id": "ref-liability",
        "source": "local_reference",
        "title": "Limitation of Liability Checklist",
        "text": "Risk allocation often includes damages exclusions, caps, carve-outs, and explicit treatment of indirect or consequential damages.",
    },
    {
        "id": "ref-data-protection",
        "source": "local_reference",
        "title": "Data Protection Checklist",
        "text": "Contracts handling personal information should describe safeguards, breach notice, processing limits, and regulatory obligations.",
    },
    {
        "id": "ref-document-structure",
        "source": "local_reference",
        "title": "Document Structure Checklist",
        "text": "Contract sections should use a consistent numbered hierarchy so headings, subclauses, and incorporated provisions remain unambiguous.",
    },
    {
        "id": "ref-cross-references",
        "source": "local_reference",
        "title": "Cross-Reference Checklist",
        "text": "Every substantive reference to a section, schedule, or appendix should resolve to material present in the executed agreement.",
    },
    {
        "id": "ref-defined-terms",
        "source": "local_reference",
        "title": "Defined Terms Checklist",
        "text": "Party roles and defined terms should be used consistently, including capitalization, throughout the agreement.",
    },
    {
        "id": "ref-internal-consistency",
        "source": "local_reference",
        "title": "Internal Consistency Checklist",
        "text": "Exceptions, overrides, and notwithstanding language should not create incompatible rights or obligations elsewhere in the contract.",
    },
    {
        "id": "ref-unilateral-discretion",
        "source": "local_reference",
        "title": "Balanced Discretion Checklist",
        "text": "Sole discretion, unilateral changes, and exclusive remedies should be limited by objective standards, notice, consent, or other balancing safeguards.",
    },
]


class LocalVectorStore:
    def __init__(self, router: ModelRouter):
        self.router = router
        self._items: List[Dict[str, str]] = []
        self._vectors: List[List[float]] = []

    def add_documents(self, documents: Iterable[Dict[str, str]]) -> None:
        docs = list(documents)
        if not docs:
            return
        vectors = self.router.embed_texts(doc["text"] for doc in docs)
        self._items.extend(docs)
        self._vectors.extend(vectors)

    def query(self, query_text: str, top_k: int = 3) -> List[Tuple[Dict[str, str], float]]:
        if not self._items:
            return []
        query_vector = self.router.embed_texts([query_text])[0]
        scored = [
            (item, self._combined_score(query_text, item, query_vector, vector))
            for item, vector in zip(self._items, self._vectors)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def _combined_score(
        self,
        query_text: str,
        item: Dict[str, str],
        query_vector: List[float],
        item_vector: List[float],
    ) -> float:
        vector_score = self._cosine(query_vector, item_vector)
        lexical_score = self._lexical_overlap(query_text, f"{item['title']} {item['text']}")
        return round((0.65 * lexical_score) + (0.35 * vector_score), 4)

    def _lexical_overlap(self, left: str, right: str) -> float:
        stopwords = {
            "the",
            "and",
            "or",
            "of",
            "to",
            "in",
            "a",
            "an",
            "for",
            "with",
            "by",
            "this",
            "that",
            "shall",
            "may",
            "any",
            "all",
        }
        left_tokens = {token for token in self._tokens(left) if token not in stopwords}
        right_tokens = {token for token in self._tokens(right) if token not in stopwords}
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = left_tokens & right_tokens
        return min(1.0, len(overlap) / max(3, min(len(left_tokens), len(right_tokens))))

    def _tokens(self, text: str) -> List[str]:
        normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
        return [token for token in normalized.split() if len(token) > 2]

    def _cosine(self, left: List[float], right: List[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if not left_norm or not right_norm:
            return 0.0
        return max(0.0, min(1.0, numerator / (left_norm * right_norm)))


class KnowledgeAgent:
    def __init__(self, router: ModelRouter):
        self.vector_store = LocalVectorStore(router)
        self.vector_store.add_documents(REFERENCE_CORPUS)

    def retrieve_for_clauses(self, clauses) -> List[Evidence]:
        all_evidence: List[Evidence] = []
        seen_ids = set()
        for clause in clauses:
            matches = self.vector_store.query(clause.text, top_k=len(REFERENCE_CORPUS))
            matches.sort(
                key=lambda pair: (
                    self._category_matches(clause.category, pair[0]["title"]),
                    pair[1],
                ),
                reverse=True,
            )
            for item, relevance in matches[:2]:
                evidence_id = f"{item['id']}::{clause.id}"
                if evidence_id in seen_ids:
                    continue
                seen_ids.add(evidence_id)
                all_evidence.append(
                    Evidence(
                        id=evidence_id,
                        source=item["source"],
                        title=item["title"],
                        text=item["text"],
                        relevance=round(relevance, 4),
                        clause_id=clause.id,
                    )
                )
        return all_evidence

    def retrieve_for_findings(
        self,
        findings: List[CandidateFinding],
        clauses: List[Clause],
    ) -> List[Evidence]:
        """Attach issue-specific references after deterministic candidates exist."""

        clause_by_id = {clause.id: clause for clause in clauses}
        retrieved: List[Evidence] = []
        for finding in findings:
            clause = clause_by_id.get(finding.clause_id or "")
            query_parts = [finding.issue_type.replace("_", " "), finding.explanation]
            if clause:
                query_parts.extend([clause.title, clause.category, clause.text])
            matches = self.vector_store.query("\n".join(query_parts), top_k=3)
            finding_evidence = [
                Evidence(
                    id=f"{item['id']}::{finding.id}",
                    source=item["source"],
                    title=item["title"],
                    text=item["text"],
                    relevance=round(relevance, 4),
                    clause_id=finding.clause_id,
                )
                for item, relevance in matches
            ]
            best_by_title = {item.title: item for item in finding.evidence}
            for item in finding_evidence:
                current = best_by_title.get(item.title)
                if current is None or item.relevance > current.relevance:
                    best_by_title[item.title] = item
            finding.evidence = sorted(
                best_by_title.values(),
                key=lambda item: item.relevance,
                reverse=True,
            )[:3]
            retrieved.extend(finding.evidence)
        return retrieved

    def _category_matches(self, category: str, title: str) -> bool:
        normalized_category = category.lower()
        normalized_title = title.lower()
        synonyms = {
            "indemnification": "indemnity",
            "governing law": "governing law",
            "termination": "termination",
            "confidentiality": "confidentiality",
            "payment": "payment",
            "assignment": "assignment",
            "limitation of liability": "liability",
            "data protection": "data protection",
        }
        target = synonyms.get(normalized_category, normalized_category)
        return target in normalized_title
