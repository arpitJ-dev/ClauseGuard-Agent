from pathlib import Path
from types import SimpleNamespace

import pytest

import clauseguard.document as document_module
from clauseguard.document import DocumentLoader, DocumentLoadError


def test_load_txt_document(tmp_path: Path):
    document_path = tmp_path / "service_agreement.txt"
    document_path.write_text(
        "SERVICE AGREEMENT\n\n1. Payment. Payment is due in 30 days.", encoding="utf-8"
    )

    document = DocumentLoader().load(document_path)

    assert document.file_type == "txt"
    assert document.title == "SERVICE AGREEMENT"
    assert "Payment" in document.text


def test_rejects_unsupported_file(tmp_path: Path):
    document_path = tmp_path / "contract.csv"
    document_path.write_text("not supported", encoding="utf-8")

    with pytest.raises(DocumentLoadError):
        DocumentLoader().load(document_path)


@pytest.mark.parametrize("suffix", [".docx", ".pdf"])
def test_reports_corrupted_binary_documents_cleanly(tmp_path: Path, suffix: str):
    document_path = tmp_path / f"corrupted{suffix}"
    document_path.write_bytes(b"this is not a valid document container")

    with pytest.raises(DocumentLoadError, match="invalid or corrupted"):
        DocumentLoader().load(document_path)


def test_rejects_empty_text_document(tmp_path: Path):
    document_path = tmp_path / "empty.txt"
    document_path.write_text("  \n\n", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="No extractable text"):
        DocumentLoader().load(document_path)


def test_collapses_repeated_full_document_pdf_text_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repeated_page = "SERVICE AGREEMENT\n\n1. Payment. " + ("Payment terms apply. " * 120)
    final_page = "2. Notices. Written notice is required."

    class FakeReader:
        is_encrypted = False
        pages = [
            SimpleNamespace(extract_text=lambda: repeated_page),
            SimpleNamespace(extract_text=lambda: repeated_page),
            SimpleNamespace(extract_text=lambda: final_page),
        ]

        def __init__(self, _handle):
            pass

    fake_pdf_library = SimpleNamespace(PdfReader=FakeReader)
    monkeypatch.setattr(document_module.importlib, "import_module", lambda _name: fake_pdf_library)

    document_path = tmp_path / "duplicate-text-layer.pdf"
    document_path.write_bytes(b"%PDF-test")

    document = DocumentLoader().load(document_path)

    assert document.text.count("SERVICE AGREEMENT") == 1
    assert final_page in document.text
