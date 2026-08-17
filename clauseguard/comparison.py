from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from clauseguard.events import ProgressCallback, notify
from clauseguard.pipeline import ClauseGuardPipeline
from clauseguard.schemas import (
    Clause,
    ClauseDelta,
    ComparisonReport,
    ComparisonRiskSignal,
    ComparisonSummary,
)

SAFEGUARD_TERMS = {
    "governing law": ["governed by", "construed in accordance with", "laws of", "law of"],
    "notice/cure": ["notice", "cure period", "failure to cure", "thirty days", "30 days"],
    "consent": ["prior written consent", "not unreasonably withheld", "mutual written agreement"],
    "reasonableness": ["reasonable", "good faith"],
    "liability limits": ["cap", "maximum", "except", "carve-out", "will not exclude"],
}


def compare_documents(
    original_path: str | Path,
    modified_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    output_formats: Iterable[str] = ("json", "markdown"),
    mock_models: bool = True,
    comparison_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    pipeline = ClauseGuardPipeline.from_env(mock_models=mock_models)
    run_id = comparison_id or str(uuid.uuid4())
    formats = tuple(output_formats)

    notify(progress_callback, "loading", "started", 5, "Loading document versions")
    original = pipeline.loader.load(original_path)
    modified = pipeline.loader.load(modified_path)
    notify(
        progress_callback,
        "loading",
        "completed",
        15,
        "Document versions loaded",
        original_file_type=original.file_type,
        modified_file_type=modified.file_type,
    )

    notify(progress_callback, "extracting", "started", 20, "Extracting comparable clauses")
    original_type, original_clauses, _ = pipeline.preprocessor.process(
        original.model_copy(update={"text": _normalize_layout(original.text)})
    )
    modified_type, modified_clauses, _ = pipeline.preprocessor.process(
        modified.model_copy(update={"text": _normalize_layout(modified.text)})
    )
    notify(
        progress_callback,
        "extracting",
        "completed",
        40,
        "Comparable clauses extracted",
        original_clause_count=len(original_clauses),
        modified_clause_count=len(modified_clauses),
    )

    notify(progress_callback, "comparing", "started", 50, "Matching contract clauses")
    matches = _match_clauses(original_clauses, modified_clauses)
    risk_signals = _risk_signals(matches)
    summary = _summary(matches)
    notify(
        progress_callback,
        "comparing",
        "completed",
        80,
        "Contract comparison completed",
        **summary.model_dump(),
        risk_signal_count=len(risk_signals),
    )

    report_model = ComparisonReport(
        comparison_id=run_id,
        original_document=str(original_path),
        modified_document=str(modified_path),
        original_type=original_type,
        modified_type=modified_type,
        original_clause_count=len(original_clauses),
        modified_clause_count=len(modified_clauses),
        summary=summary,
        clause_deltas=[_public_delta(delta) for delta in matches],
        risk_signals=risk_signals,
        notes=[
            "Comparison mode uses both documents and is intentionally separate from standalone benchmark PRF evaluation.",
            "Signals are deterministic review hints for changed clauses, not broad legal accuracy metrics.",
        ],
    )
    report = report_model.model_dump(mode="json")

    notify(progress_callback, "reporting", "started", 90, "Writing comparison report")
    if output_dir:
        write_comparison_report(report, output_dir, formats)
    notify(
        progress_callback,
        "reporting",
        "completed",
        98,
        "Comparison report written",
        output_dir=str(output_dir) if output_dir else None,
    )
    return report


def write_comparison_report(
    report: dict[str, Any],
    output_dir: str | Path,
    output_formats: Iterable[str] = ("json", "markdown"),
) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    formats = tuple(output_formats)
    unknown = set(formats) - {"json", "markdown"}
    if unknown:
        raise ValueError(f"Unsupported comparison output format: {sorted(unknown)}")
    if "json" in formats:
        (target / "comparison_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    if "markdown" in formats:
        (target / "comparison_report.md").write_text(
            comparison_to_markdown(report), encoding="utf-8"
        )


def comparison_to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# ClauseGuard Comparison Report",
        "",
        f"**Original:** {report['original_document']}",
        f"**Modified:** {report['modified_document']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Original clauses | {report['original_clause_count']} |",
        f"| Modified clauses | {report['modified_clause_count']} |",
        f"| Matched clauses | {summary['matched']} |",
        f"| Changed clauses | {summary['changed']} |",
        f"| Added clauses | {summary['added']} |",
        f"| Removed clauses | {summary['removed']} |",
        "",
        "## Risk Signals",
        "",
    ]

    signals = report["risk_signals"]
    if not signals:
        lines.append("No comparison risk signals were detected.")
    for signal in signals:
        lines.extend(
            [
                f"### {signal['type']}",
                "",
                f"- Clause: {signal['clause']}",
                f"- Detail: {signal['detail']}",
                f"- Severity: {signal['severity']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Changed Clauses",
            "",
            "| Modified Clause | Original Clause | Similarity | Status |",
            "|---|---|---:|---|",
        ]
    )
    for delta in report["clause_deltas"]:
        if delta["status"] == "unchanged":
            continue
        lines.append(
            "| "
            f"{delta.get('modified_title') or 'none'} | "
            f"{delta.get('original_title') or 'none'} | "
            f"{delta['similarity']:.2f} | "
            f"{delta['status']} |"
        )

    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in report["notes"])
    lines.append("")
    return "\n".join(lines)


def _match_clauses(
    original_clauses: list[Clause], modified_clauses: list[Clause]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    used_original: set[str] = set()

    for modified in modified_clauses:
        best_original = None
        best_score = 0.0
        for original in original_clauses:
            if original.id in used_original:
                continue
            score = _clause_similarity(original, modified)
            if score > best_score:
                best_original = original
                best_score = score

        if best_original and best_score >= 0.30:
            used_original.add(best_original.id)
            status = (
                "unchanged"
                if _normalize_text(best_original.text) == _normalize_text(modified.text)
                else "changed"
            )
            matches.append(_delta(status, best_original, modified, best_score))
        else:
            matches.append(_delta("added", None, modified, 0.0))

    for original in original_clauses:
        if original.id not in used_original:
            matches.append(_delta("removed", original, None, 0.0))

    return matches


def _delta(
    status: str, original: Clause | None, modified: Clause | None, similarity: float
) -> dict[str, Any]:
    return {
        "status": status,
        "similarity": round(similarity, 4),
        "original_clause_id": original.id if original else None,
        "original_title": original.title if original else None,
        "original_category": original.category if original else None,
        "modified_clause_id": modified.id if modified else None,
        "modified_title": modified.title if modified else None,
        "modified_category": modified.category if modified else None,
        "original_risk_terms": original.risk_terms if original else [],
        "modified_risk_terms": modified.risk_terms if modified else [],
        "original_preview": _preview(original.text if original else ""),
        "modified_preview": _preview(modified.text if modified else ""),
        "_original_text": original.text if original else "",
        "_modified_text": modified.text if modified else "",
    }


def _summary(matches: list[dict[str, Any]]) -> ComparisonSummary:
    return ComparisonSummary(
        matched=sum(1 for item in matches if item["status"] in {"changed", "unchanged"}),
        changed=sum(1 for item in matches if item["status"] == "changed"),
        added=sum(1 for item in matches if item["status"] == "added"),
        removed=sum(1 for item in matches if item["status"] == "removed"),
    )


def _risk_signals(matches: list[dict[str, Any]]) -> list[ComparisonRiskSignal]:
    signals: list[ComparisonRiskSignal] = []
    for delta in matches:
        if delta["status"] == "unchanged":
            continue
        original = f"{delta.get('original_title') or ''}\n{delta.get('_original_text') or ''}"
        modified = f"{delta.get('modified_title') or ''}\n{delta.get('_modified_text') or ''}"
        original_lower = original.lower()
        modified_lower = modified.lower()
        clause_name = str(
            delta.get("modified_title") or delta.get("original_title") or "Document-level"
        )

        added_risk_terms = sorted(
            set(delta["modified_risk_terms"]) - set(delta["original_risk_terms"])
        )
        if added_risk_terms:
            signals.append(
                ComparisonRiskSignal(
                    type="added_risk_terms",
                    clause=clause_name,
                    detail=", ".join(added_risk_terms),
                    severity="MEDIUM",
                )
            )

        removed_safeguards = [
            label
            for label, terms in SAFEGUARD_TERMS.items()
            if any(term in original_lower for term in terms)
            and not any(term in modified_lower for term in terms)
        ]
        if removed_safeguards:
            signals.append(
                ComparisonRiskSignal(
                    type="removed_safeguards",
                    clause=clause_name,
                    detail=", ".join(removed_safeguards),
                    severity="HIGH",
                )
            )

        if (
            _looks_like_governing_law(delta)
            and _has_dispute_text(modified_lower)
            and not _has_governing_standard(modified_lower)
        ):
            signals.append(
                ComparisonRiskSignal(
                    type="incomplete_governing_law",
                    clause=clause_name,
                    detail=(
                        "Modified text keeps dispute/forum mechanics but lacks a "
                        "governing-law standard."
                    ),
                    severity="HIGH",
                )
            )

    return signals[:40]


def _looks_like_governing_law(delta: dict[str, Any]) -> bool:
    context = " ".join(
        str(delta.get(key) or "")
        for key in (
            "original_title",
            "original_category",
            "modified_title",
            "modified_category",
            "_modified_text",
        )
    ).lower()
    return "governing law" in context


def _public_delta(delta: dict[str, Any]) -> ClauseDelta:
    return ClauseDelta.model_validate(
        {key: value for key, value in delta.items() if not key.startswith("_")}
    )


def _has_dispute_text(text: str) -> bool:
    return any(term in text for term in ["dispute", "claim", "arbitration", "venue", "forum"])


def _has_governing_standard(text: str) -> bool:
    return bool(
        re.search(
            r"\b(governed by|construed in accordance with|laws of|law of|state of|commonwealth of)\b",
            text,
        )
    )


def _clause_similarity(original: Clause, modified: Clause) -> float:
    heading_score = (
        1.0
        if _heading_label(original) and _heading_label(original) == _heading_label(modified)
        else 0.0
    )
    title_score = _jaccard(_tokens(original.title), _tokens(modified.title))
    text_score = _jaccard(_tokens(original.text), _tokens(modified.text))
    category_score = 1.0 if original.category == modified.category else 0.0
    return (
        (heading_score * 0.30)
        + (title_score * 0.25)
        + (text_score * 0.30)
        + (category_score * 0.15)
    )


def _heading_label(clause: Clause) -> str:
    source = clause.title or clause.text
    source = re.sub(r"^\s*\d{1,2}(?:\.\d+)*[\.)]?\s*", "", source.strip())
    label = source.split(".", 1)[0]
    tokens = _tokens(label)
    return " ".join(sorted(tokens))


def _tokens(text: str) -> set[str]:
    stopwords = {"the", "and", "or", "of", "to", "in", "a", "an", "this", "that", "shall", "may"}
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in stopwords
    }


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _normalize_layout(text: str) -> str:
    flattened = re.sub(r"\s+", " ", text).strip()
    return re.sub(
        r"\s+(?=\d{1,2}(?:\.\d{1,2})*[\.)]?\s+[A-Z][A-Za-z][A-Za-z ,/&()'\-]{2,80}\.)",
        "\n\n",
        flattened,
    )


def _preview(text: str, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]
