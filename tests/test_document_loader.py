from pathlib import Path

import pytest

from legal_lm.document import DocumentLoadError, DocumentLoader


def test_load_txt_document(tmp_path: Path):
    document_path = tmp_path / "service_agreement.txt"
    document_path.write_text("SERVICE AGREEMENT\n\n1. Payment. Payment is due in 30 days.", encoding="utf-8")

    document = DocumentLoader().load(document_path)

    assert document.file_type == "txt"
    assert document.title == "SERVICE AGREEMENT"
    assert "Payment" in document.text


def test_rejects_unsupported_file(tmp_path: Path):
    document_path = tmp_path / "contract.csv"
    document_path.write_text("not supported", encoding="utf-8")

    with pytest.raises(DocumentLoadError):
        DocumentLoader().load(document_path)
