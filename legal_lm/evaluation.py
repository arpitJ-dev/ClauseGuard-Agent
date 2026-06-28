from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Sequence

from legal_lm.pipeline import LegalAnalysisPipeline
from legal_lm.schemas import AnalysisReport


class EvaluationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    document_path: Path
    expected_issue_types: set[str]
    description: str = ""
    expected_absent_issue_types: set[str] = field(default_factory=set)


def load_benchmark(benchmark_path: str | Path) -> List[BenchmarkCase]:
    path = Path(benchmark_path)
    if not path.exists():
        raise EvaluationError(f"Benchmark file not found: {path}")

    cases: List[BenchmarkCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

        case_id = str(payload.get("id") or "").strip()
        document = str(payload.get("document") or "").strip()
        if not case_id or not document:
            raise EvaluationError(f"Benchmark case at {path}:{line_number} must include id and document.")

        document_path = _resolve_document_path(path, document)
        if not document_path.exists():
            raise EvaluationError(f"Benchmark document not found for case {case_id}: {document_path}")

        expected_issue_types = _issue_type_set(payload.get("expected_issue_types", []))
        expected_absent_issue_types = _issue_type_set(payload.get("expected_absent_issue_types", []))
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                document_path=document_path,
                expected_issue_types=expected_issue_types,
                expected_absent_issue_types=expected_absent_issue_types,
                description=str(payload.get("description") or "").strip(),
            )
        )

    if not cases:
        raise EvaluationError(f"Benchmark file contains no cases: {path}")
    return cases


def classification_metrics(expected: Iterable[str], predicted: Iterable[str]) -> dict[str, Any]:
    expected_set = set(expected)
    predicted_set = set(predicted)
    true_positive = expected_set & predicted_set
    false_positive = predicted_set - expected_set
    false_negative = expected_set - predicted_set

    precision_denominator = len(true_positive) + len(false_positive)
    recall_denominator = len(true_positive) + len(false_negative)
    precision = len(true_positive) / precision_denominator if precision_denominator else 1.0
    recall = len(true_positive) / recall_denominator if recall_denominator else 1.0
    f1 = 0.0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall)

    return {
        "true_positive": len(true_positive),
        "false_positive": len(false_positive),
        "false_negative": len(false_negative),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positive_issue_types": sorted(true_positive),
        "false_positive_issue_types": sorted(false_positive),
        "false_negative_issue_types": sorted(false_negative),
    }


def evaluate_report(
    report: AnalysisReport,
    benchmark_case: BenchmarkCase,
    scored_issue_types: set[str] | None = None,
) -> dict[str, Any]:
    accepted_findings = [finding for finding in report.findings if finding.accepted]
    predicted_issue_types = {finding.issue_type for finding in accepted_findings}
    scored_labels = scored_issue_types or (benchmark_case.expected_issue_types | benchmark_case.expected_absent_issue_types)
    scored_predicted_issue_types = predicted_issue_types & scored_labels if scored_labels else predicted_issue_types
    out_of_scope_predicted_issue_types = predicted_issue_types - scored_labels if scored_labels else set()
    metrics = classification_metrics(benchmark_case.expected_issue_types, scored_predicted_issue_types)

    unexpected_absent_hits = sorted(predicted_issue_types & benchmark_case.expected_absent_issue_types)
    return {
        "case_id": benchmark_case.case_id,
        "description": benchmark_case.description,
        "document": str(benchmark_case.document_path),
        "document_type": report.document_type,
        "clause_count": len(report.clauses),
        "expected_issue_types": sorted(benchmark_case.expected_issue_types),
        "predicted_issue_types": sorted(predicted_issue_types),
        "scored_predicted_issue_types": sorted(scored_predicted_issue_types),
        "out_of_scope_predicted_issue_types": sorted(out_of_scope_predicted_issue_types),
        "unexpected_absent_hits": unexpected_absent_hits,
        "accepted_findings": [
            {
                "issue_type": finding.issue_type,
                "severity": finding.severity,
                "clause": finding.clause_title or finding.clause_id or "Document-level",
                "final_score": round(finding.component_scores.final, 4),
            }
            for finding in accepted_findings
        ],
        **metrics,
    }


def run_benchmark(
    benchmark_path: str | Path,
    output_dir: str | Path = "analysis_outputs/benchmark_evaluation",
    *,
    mock_models: bool = True,
    max_cases: int | None = None,
    allow_multiple_real_cases: bool = False,
) -> dict[str, Any]:
    cases = load_benchmark(benchmark_path)
    if max_cases is not None and max_cases < 1:
        raise EvaluationError("max_cases must be at least 1 when provided.")

    if not mock_models:
        if max_cases is None:
            max_cases = 1
        if max_cases > 1 and not allow_multiple_real_cases:
            raise EvaluationError(
                "Real-model benchmark runs are capped to one case by default. "
                "Pass --allow-multiple-real-cases only after checking Groq console limits."
            )

    selected_cases = cases[:max_cases] if max_cases else cases
    scored_issue_types = _scored_issue_types(selected_cases)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    pipeline = LegalAnalysisPipeline.from_env(mock_models=mock_models)
    case_results: List[dict[str, Any]] = []
    for benchmark_case in selected_cases:
        case_output_dir = target / "case_reports" / _safe_name(benchmark_case.case_id)
        report = pipeline.analyze(benchmark_case.document_path, output_dir=case_output_dir, include_rewrites=False)
        case_result = evaluate_report(report, benchmark_case, scored_issue_types)
        case_result["report_json"] = str(case_output_dir / "analysis_report.json")
        case_result["report_markdown"] = str(case_output_dir / "analysis_report.md")
        case_results.append(case_result)

    summary = {
        "benchmark": str(Path(benchmark_path)),
        "mode": "mock/local" if mock_models else "real-groq",
        "cases_available": len(cases),
        "cases_evaluated": len(case_results),
        "scored_issue_types": sorted(scored_issue_types),
        "aggregate": _aggregate_metrics(case_results),
        "per_issue_type": _per_issue_metrics(case_results, scored_issue_types),
        "usage_snapshot": pipeline.router.usage_limiter.snapshot(),
        "configured_caps": pipeline.config.usage_limits(),
        "cases": case_results,
        "notes": [
            "Metrics are issue-type benchmark metrics for the labeled cases, not broad legal accuracy.",
            "Predictions outside the benchmark label set are reported separately and not counted as false positives.",
            "Mock/local mode does not reserve Groq requests or input-token budget.",
            "Real-model mode uses the same per-run request and estimated input-token caps shown by `python -m legal_lm models`.",
        ],
    }

    (target / "benchmark_evaluation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (target / "benchmark_evaluation.md").write_text(_to_markdown(summary), encoding="utf-8")
    return summary


def _aggregate_metrics(case_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    true_positive = sum(int(item["true_positive"]) for item in case_results)
    false_positive = sum(int(item["false_positive"]) for item in case_results)
    false_negative = sum(int(item["false_negative"]) for item in case_results)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = true_positive / precision_denominator if precision_denominator else 1.0
    recall = true_positive / recall_denominator if recall_denominator else 1.0
    f1 = 0.0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall)
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _per_issue_metrics(case_results: Sequence[dict[str, Any]], scored_issue_types: set[str]) -> list[dict[str, Any]]:
    labels = sorted(scored_issue_types)
    rows = []
    for label in labels:
        true_positive = 0
        false_positive = 0
        false_negative = 0
        for case in case_results:
            expected = set(case["expected_issue_types"])
            predicted = set(case["scored_predicted_issue_types"])
            if label in expected and label in predicted:
                true_positive += 1
            elif label not in expected and label in predicted:
                false_positive += 1
            elif label in expected and label not in predicted:
                false_negative += 1
        precision_denominator = true_positive + false_positive
        recall_denominator = true_positive + false_negative
        precision = true_positive / precision_denominator if precision_denominator else 1.0
        recall = true_positive / recall_denominator if recall_denominator else None
        f1 = None if recall is None else (0.0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall))
        rows.append(
            {
                "issue_type": label,
                "true_positive": true_positive,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "expected_support": recall_denominator,
                "predicted_count": precision_denominator,
                "precision": round(precision, 4),
                "recall": round(recall, 4) if recall is not None else None,
                "f1": round(f1, 4) if f1 is not None else None,
            }
        )
    return rows


def _scored_issue_types(cases: Sequence[BenchmarkCase]) -> set[str]:
    return {
        label
        for benchmark_case in cases
        for label in benchmark_case.expected_issue_types | benchmark_case.expected_absent_issue_types
    }


def _issue_type_set(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise EvaluationError("Benchmark issue type fields must be arrays.")
    return {str(item).strip() for item in raw if str(item).strip()}


def _resolve_document_path(benchmark_path: Path, document: str) -> Path:
    document_path = Path(document)
    if document_path.is_absolute():
        return document_path

    benchmark_relative = (benchmark_path.parent / document_path).resolve()
    if benchmark_relative.exists():
        return benchmark_relative

    cwd_relative = document_path.resolve()
    if cwd_relative.exists():
        return cwd_relative

    return benchmark_relative


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-") or "case"


def _to_markdown(summary: dict[str, Any]) -> str:
    aggregate = summary["aggregate"]
    lines = [
        "# Benchmark Evaluation",
        "",
        f"**Mode:** {summary['mode']}",
        f"**Cases evaluated:** {summary['cases_evaluated']} of {summary['cases_available']}",
        "",
        "## Aggregate Metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| True positives | {aggregate['true_positive']} |",
        f"| False positives | {aggregate['false_positive']} |",
        f"| False negatives | {aggregate['false_negative']} |",
        f"| Precision | {aggregate['precision']:.4f} |",
        f"| Recall | {aggregate['recall']:.4f} |",
        f"| F1 | {aggregate['f1']:.4f} |",
        "",
        "## Case Results",
        "",
        "| Case | Expected | Scored Predictions | Precision | Recall | F1 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for case in summary["cases"]:
        lines.append(
            "| "
            f"{case['case_id']} | "
            f"{_format_issue_list(case['expected_issue_types'])} | "
            f"{_format_issue_list(case['scored_predicted_issue_types'])} | "
            f"{case['precision']:.4f} | "
            f"{case['recall']:.4f} | "
            f"{case['f1']:.4f} |"
        )

    out_of_scope_cases = [
        case for case in summary["cases"] if case.get("out_of_scope_predicted_issue_types")
    ]
    if out_of_scope_cases:
        lines.extend(
            [
                "",
                "## Out-of-Scope Predictions",
                "",
                "| Case | Predicted Issue Types Not Scored By This Benchmark |",
                "|---|---|",
            ]
        )
        for case in out_of_scope_cases:
            lines.append(
                "| "
                f"{case['case_id']} | "
                f"{_format_issue_list(case['out_of_scope_predicted_issue_types'])} |"
            )

    lines.extend(
        [
            "",
            "## Per-Issue Metrics",
            "",
            "| Issue Type | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for issue in summary["per_issue_type"]:
        lines.append(
            "| "
            f"{issue['issue_type']} | "
            f"{issue['true_positive']} | "
            f"{issue['false_positive']} | "
            f"{issue['false_negative']} | "
            f"{_format_metric(issue['precision'])} | "
            f"{_format_metric(issue['recall'])} | "
            f"{_format_metric(issue['f1'])} |"
        )

    lines.extend(
        [
            "",
            "## Usage Snapshot",
            "",
            "| Role | Model | Requests | Cap | Estimated input tokens | Cap |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    usage = summary["usage_snapshot"]
    caps = summary["configured_caps"]
    for role in ("extraction", "reasoning", "verifier", "embedding"):
        role_usage = usage[role]
        role_caps = caps[role]
        lines.append(
            "| "
            f"{role} | {role_caps['model']} | "
            f"{role_usage['requests']} | {role_caps['max_requests']} | "
            f"{role_usage['input_tokens']} | {role_caps['max_input_tokens']} |"
        )

    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in summary["notes"])
    lines.append("")
    return "\n".join(lines)


def _format_issue_list(values: Iterable[str]) -> str:
    items = sorted(values)
    return ", ".join(items) if items else "none"


def _format_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
