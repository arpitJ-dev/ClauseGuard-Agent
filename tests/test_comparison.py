from pathlib import Path

from clauseguard.comparison import compare_documents


def test_compare_documents_reports_changes_without_cloud_calls(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    original = tmp_path / "original.txt"
    modified = tmp_path / "modified.txt"
    original.write_text(
        """
        SERVICES AGREEMENT

        1. Governing Law. This Agreement and all disputes are governed by the laws of California.

        2. Returns. Customer may return defective products with prior written notice.
        """,
        encoding="utf-8",
    )
    modified.write_text(
        """
        SERVICES AGREEMENT

        1. Governing Law. All disputes shall be resolved by arbitration in Los Angeles, California.

        2. Returns. Provider may reject returns in its sole discretion and products are sold as is.
        """,
        encoding="utf-8",
    )

    output_dir = tmp_path / "comparison"
    report = compare_documents(original, modified, output_dir=output_dir, mock_models=True)

    assert report["summary"]["matched"] == 2
    assert report["summary"]["changed"] == 2
    assert any(signal["type"] == "incomplete_governing_law" for signal in report["risk_signals"])
    assert any(signal["type"] == "added_risk_terms" for signal in report["risk_signals"])
    assert (output_dir / "comparison_report.json").exists()
    assert (output_dir / "comparison_report.md").exists()
    assert "_original_text" not in report["clause_deltas"][0]


def test_compare_documents_is_separate_from_benchmark_inputs():
    import inspect

    from clauseguard import evaluation

    source = inspect.getsource(evaluation.run_benchmark)

    assert "original_document" not in source
    assert "compare_documents" not in source


def test_compare_documents_is_invariant_to_line_wrapping(tmp_path: Path):
    original = tmp_path / "paragraph-layout.txt"
    wrapped = tmp_path / "wrapped-layout.txt"
    text = (
        "SERVICES AGREEMENT\n\n"
        "1. Payment. Customer shall pay each undisputed invoice within thirty days.\n\n"
        "2. Notices. Each notice must be delivered in writing to the stated address."
    )
    original.write_text(text, encoding="utf-8")
    wrapped.write_text("\n".join(text.split()), encoding="utf-8")

    report = compare_documents(original, wrapped, mock_models=True)

    assert report["summary"] == {"matched": 2, "changed": 0, "added": 0, "removed": 0}
