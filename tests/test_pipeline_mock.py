from pathlib import Path

from legal_lm.pipeline import LegalAnalysisPipeline


def test_pipeline_runs_end_to_end_with_mock_models(tmp_path: Path):
    document_path = tmp_path / "agreement.txt"
    document_path.write_text(
        """
        SERVICES AGREEMENT

        1. Payment. Customer shall make payment as agreed by the parties.

        2. Termination. Provider may terminate immediately for any reason.

        3. Indemnity. Customer shall indemnify Provider from any and all claims without limitation.
        """,
        encoding="utf-8",
    )

    output_dir = tmp_path / "outputs"
    pipeline = LegalAnalysisPipeline.from_env(mock_models=True)
    report = pipeline.analyze(document_path, output_dir=output_dir)

    assert report.document_type == "Service Agreement"
    assert report.clauses
    assert any(finding.accepted for finding in report.findings)
    assert any(finding.component_scores.final > 0 for finding in report.findings)
    assert (output_dir / "analysis_report.json").exists()
    assert (output_dir / "analysis_report.md").exists()
