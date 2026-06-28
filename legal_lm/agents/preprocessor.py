from __future__ import annotations

import re
from typing import Dict, List, Tuple

from legal_lm.model_router import ModelResponseError, ModelRouter
from legal_lm.schemas import Clause, LegalEntity, LoadedDocument


RISK_TERMS = [
    "sole discretion",
    "at its discretion",
    "as it sees fit",
    "deems appropriate",
    "will endeavor",
    "should attempt",
    "unlimited",
    "no liability",
    "as is",
    "exclusive remedy",
]

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Confidentiality": ["confidential", "non-disclosure", "proprietary"],
    "Termination": ["terminate", "termination", "cure period"],
    "Governing Law": ["governing law", "venue", "jurisdiction", "laws of", "law of"],
    "Indemnification": ["indemnify", "indemnification", "hold harmless"],
    "Payment": ["payment", "invoice", "fees", "taxes"],
    "Assignment": ["assign", "assignment"],
    "Limitation of Liability": ["liability", "consequential", "damages", "cap"],
    "Data Protection": ["personal information", "data", "security", "breach"],
    "Notices": ["notices", "written notice", "communications"],
}


class PreprocessorAgent:
    def __init__(self, router: ModelRouter):
        self.router = router

    def process(self, document: LoadedDocument) -> Tuple[str, List[Clause], List[LegalEntity]]:
        deterministic_clauses = self._extract_clauses(document.text)
        document_type = self._classify_document(document.title, document.text)

        try:
            model_output = self.router.generate_json(
                "extraction",
                "Return only JSON with keys document_type and clauses. Each clause needs title, text, category.",
                document.text[:12000],
            )
        except ModelResponseError:
            model_output = {}

        if isinstance(model_output.get("document_type"), str) and model_output["document_type"].strip():
            document_type = model_output["document_type"].strip()

        model_clauses = self._clauses_from_model(model_output)
        clauses = self._select_clause_set(deterministic_clauses, model_clauses)
        if not clauses:
            clauses = [
                Clause(
                    id="clause-001",
                    order=1,
                    title="Document Body",
                    text=document.text[:6000],
                    category="General",
                    risk_terms=self._risk_terms(document.text),
                )
            ]

        entities = self._extract_entities(document.text)
        return document_type, clauses, entities

    def _select_clause_set(self, deterministic_clauses: List[Clause], model_clauses: List[Clause]) -> List[Clause]:
        if not model_clauses:
            return deterministic_clauses
        if not deterministic_clauses:
            return model_clauses

        # Model extraction may summarize long contracts and drop later clauses.
        # Keep deterministic full-document coverage when model output is clearly partial.
        minimum_coverage = max(2, int(len(deterministic_clauses) * 0.75))
        if len(model_clauses) < minimum_coverage:
            return deterministic_clauses
        return model_clauses

    def _extract_clauses(self, text: str) -> List[Clause]:
        chunks = self._split_into_chunks(text)
        clauses = []
        for index, chunk in enumerate(chunks, start=1):
            title = self._infer_title(chunk, index)
            clauses.append(
                Clause(
                    id=f"clause-{index:03d}",
                    order=index,
                    title=title,
                    text=chunk,
                    category=self._categorize(chunk),
                    risk_terms=self._risk_terms(chunk),
                )
            )
        return clauses

    def _split_into_chunks(self, text: str) -> List[str]:
        normalized = re.sub(r"\n\s*(\d{1,2}[\.\)]\s+)", r"\n\n\1", text)
        normalized = re.sub(
            r"(?<!\n)\s+(?=\d{1,2}(?:\.\d{1,2})*\s+[A-Z][A-Za-z][A-Za-z ,/&()'\-]{2,80}\.)",
            "\n\n",
            normalized,
        )
        chunks = []
        for raw_chunk in re.split(r"\n\s*\n", normalized):
            chunk = raw_chunk.strip()
            if len(chunk) < 35:
                continue
            if len(chunk) < 90 and re.fullmatch(r"[A-Z0-9 ,.'\-]+(?:AGREEMENT|CONTRACT)[A-Z0-9 ,.'\-]*", chunk):
                continue
            chunks.append(chunk)
        if len(chunks) >= 2:
            return chunks[:80]

        sentences = re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", text)
        rebuilt: List[str] = []
        buffer: List[str] = []
        for sentence in sentences:
            buffer.append(sentence.strip())
            if sum(len(part) for part in buffer) > 500:
                rebuilt.append(" ".join(buffer))
                buffer = []
        if buffer:
            rebuilt.append(" ".join(buffer))
        return [chunk for chunk in rebuilt if len(chunk) >= 60][:80]

    def _clauses_from_model(self, payload: Dict) -> List[Clause]:
        raw_clauses = payload.get("clauses")
        if not isinstance(raw_clauses, list):
            return []
        clauses = []
        for index, raw in enumerate(raw_clauses, start=1):
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or raw.get("Text") or "").strip()
            if len(text) < 30:
                continue
            title = str(raw.get("title") or raw.get("Title") or self._infer_title(text, index)).strip()
            category = str(raw.get("category") or raw.get("Category") or self._categorize(text)).strip()
            clauses.append(
                Clause(
                    id=f"clause-{index:03d}",
                    order=index,
                    title=title[:120],
                    text=text,
                    category=category[:80] or "General",
                    risk_terms=self._risk_terms(text),
                )
            )
        return clauses

    def _infer_title(self, chunk: str, index: int) -> str:
        first_line = chunk.splitlines()[0].strip()
        cleaned = re.sub(r"^\d{1,2}[\.\)]\s*", "", first_line)
        if len(cleaned) <= 90:
            return cleaned
        category = self._categorize(chunk)
        return category if category != "General" else f"Clause {index}"

    def _categorize(self, text: str) -> str:
        lower = text.lower()
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword in lower for keyword in keywords):
                return category
        return "General"

    def _risk_terms(self, text: str) -> List[str]:
        lower = text.lower()
        patterns = {
            "sole discretion": r"\bsole\s+discretion\b",
            "at its discretion": r"\bat\s+its\s+discretion\b",
            "as it sees fit": r"\bas\s+it\s+sees\s+fit\b",
            "deems appropriate": r"\bdeems\s+appropriate\b",
            "will endeavor": r"\bwill\s+endeavo[u]?r\b",
            "should attempt": r"\bshould\s+attempt\b",
            "unlimited": r"\bunlimited\b",
            "no liability": r"\bno\s+liability\b",
            "as is": r"(?:\"as\s+is\"|'as\s+is'|\bas-is\b|\bprovided\s+as\s+is\b)",
            "exclusive remedy": r"\bexclusive\s+remedy\b",
        }
        return [term for term in RISK_TERMS if re.search(patterns[term], lower)]

    def _classify_document(self, title: str, text: str) -> str:
        sample = f"{title}\n{text[:2000]}".lower()
        labels = {
            "services agreement": "Service Agreement",
            "service agreement": "Service Agreement",
            "affiliate agreement": "Affiliate Agreement",
            "supply agreement": "Supply Agreement",
            "consulting agreement": "Consulting Agreement",
            "reseller agreement": "Reseller Agreement",
            "distribution agreement": "Distribution Agreement",
            "agency agreement": "Agency Agreement",
            "joint venture agreement": "Joint Venture Agreement",
            "endorsement agreement": "Endorsement Agreement",
            "co-branding agreement": "Co-Branding Agreement",
        }
        for candidate, label in labels.items():
            if candidate in sample:
                return label
        if "agreement" in sample:
            return "Commercial Agreement"
        if "contract" in sample:
            return "Contract"
        return "Legal Document"

    def _extract_entities(self, text: str) -> List[LegalEntity]:
        entities: List[LegalEntity] = []
        patterns = [
            ("DATE", r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b"),
            ("MONEY", r"\$\s?\d[\d,]*(?:\.\d{2})?"),
            ("PERCENT", r"\b\d+(?:\.\d+)?%"),
            ("ORG", r"\b[A-Z][A-Za-z0-9&.,'\- ]{2,}\s+(?:Inc\.?|LLC|Ltd\.?|Corporation|Corp\.?|Company|Co\.?)\b"),
            ("JURISDICTION", r"\b(?:State of\s+[A-Z][a-z]+|laws of\s+[A-Z][A-Za-z ]+|United States)\b"),
        ]
        seen = set()
        for label, pattern in patterns:
            for match in re.finditer(pattern, text):
                value = match.group(0).strip()
                key = (label, value.lower())
                if key in seen:
                    continue
                seen.add(key)
                entities.append(LegalEntity(text=value, label=label))
        return entities[:120]
