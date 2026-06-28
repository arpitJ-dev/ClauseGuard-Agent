from pathlib import Path

import pytest

from legal_lm.evaluation import BenchmarkCase, EvaluationError, classification_metrics, evaluate_report, load_benchmark, run_benchmark
from legal_lm.schemas import AnalysisReport, ComponentScores, Finding


def test_classification_metrics_counts_tp_fp_fn():
    metrics = classification_metrics({"missing_governing_law", "uncapped_indemnity"}, {"missing_governing_law", "risky_language"})

    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5


def test_evaluate_report_separates_out_of_scope_predictions(tmp_path: Path):
    scores = ComponentScores(
        deterministic_rules=0.8,
        rag_evidence=0.8,
        primary_reasoning=0.8,
        verifier_agreement=0.8,
        clause_structure=0.8,
        final=0.8,
        weights={},
    )
    report = AnalysisReport(
        document_id="doc-1",
        file_path=str(tmp_path / "contract.txt"),
        title="Contract",
        document_type="Agreement",
        summary="summary",
        clauses=[],
        entities=[],
        evidence=[],
        findings=[
            Finding(
                id="finding-1",
                issue_type="internal_contradiction",
                severity="HIGH",
                explanation="supported",
                component_scores=scores,
                accepted=True,
                model_confidence=0.8,
                verifier_confidence=0.8,
            ),
            Finding(
                id="finding-2",
                issue_type="uncapped_indemnity",
                severity="HIGH",
                explanation="extra legal risk not labeled by this benchmark",
                component_scores=scores,
                accepted=True,
                model_confidence=0.8,
                verifier_confidence=0.8,
            ),
        ],
        rewrites=[],
    )
    benchmark_case = BenchmarkCase(
        case_id="case-1",
        document_path=tmp_path / "contract.txt",
        expected_issue_types={"internal_contradiction"},
    )

    result = evaluate_report(report, benchmark_case, scored_issue_types={"internal_contradiction"})

    assert result["precision"] == 1.0
    assert result["false_positive"] == 0
    assert result["scored_predicted_issue_types"] == ["internal_contradiction"]
    assert result["out_of_scope_predicted_issue_types"] == ["uncapped_indemnity"]


def test_load_benchmark_resolves_relative_documents(tmp_path: Path):
    document = tmp_path / "contract.txt"
    document.write_text("SERVICES AGREEMENT\n\n1. Payment. Customer shall pay within thirty days.", encoding="utf-8")
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        '{"id":"case-1","document":"contract.txt","expected_issue_types":["missing_governing_law"]}\n',
        encoding="utf-8",
    )

    cases = load_benchmark(benchmark)

    assert len(cases) == 1
    assert cases[0].document_path == document.resolve()
    assert cases[0].expected_issue_types == {"missing_governing_law"}


def test_run_benchmark_mock_mode_does_not_require_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    document = tmp_path / "contract.txt"
    document.write_text(
        """
        SERVICES AGREEMENT

        1. Payment. Customer shall make payment as agreed by the parties.

        2. Termination. Provider may terminate immediately for any reason.
        """,
        encoding="utf-8",
    )
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        '{"id":"case-1","document":"contract.txt","expected_issue_types":["missing_governing_law","missing_confidentiality","vague_payment_terms","termination_without_notice"]}\n',
        encoding="utf-8",
    )

    output_dir = tmp_path / "results"
    summary = run_benchmark(benchmark, output_dir=output_dir, mock_models=True)

    assert summary["mode"] == "mock/local"
    assert summary["cases_evaluated"] == 1
    assert summary["usage_snapshot"]["reasoning"]["requests"] == 0
    assert summary["usage_snapshot"]["verifier"]["requests"] == 0
    assert (output_dir / "benchmark_evaluation.json").exists()
    assert (output_dir / "benchmark_evaluation.md").exists()


def test_real_benchmark_multiple_cases_requires_explicit_override(tmp_path: Path):
    document_one = tmp_path / "one.txt"
    document_two = tmp_path / "two.txt"
    document_one.write_text("SERVICES AGREEMENT\n\n1. Payment. Customer shall pay within thirty days.", encoding="utf-8")
    document_two.write_text("SERVICES AGREEMENT\n\n1. Payment. Customer shall pay within thirty days.", encoding="utf-8")
    benchmark = tmp_path / "benchmark.jsonl"
    benchmark.write_text(
        "\n".join(
            [
                '{"id":"case-1","document":"one.txt","expected_issue_types":[]}',
                '{"id":"case-2","document":"two.txt","expected_issue_types":[]}',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(EvaluationError, match="capped to one case"):
        run_benchmark(benchmark, output_dir=tmp_path / "results", mock_models=False, max_cases=2)
