from pathlib import Path

from legal_lm.dataset_benchmark import build_repo_dataset_benchmark


def test_build_repo_dataset_benchmark_pairs_modified_file_and_maps_labels(tmp_path: Path):
    originals = tmp_path / "Original_files"
    perturbations = tmp_path / "Perturbations"
    originals.mkdir()
    perturbations.mkdir()

    original = originals / "ACME_01_01_2020-SERVICESAGREEMENT.txt"
    modified = perturbations / "modified_ACME_01_01_2020-SERVICESAGREEMENT.txt.txt"
    metadata = perturbations / "perturbed_ACME_01_01_2020-SERVICESAGREEMENT.txt.json"

    original.write_text("SERVICES AGREEMENT\n\n1. Assignment. Neither party may assign without consent.", encoding="utf-8")
    modified.write_text("SERVICES AGREEMENT\n\n1. Assignment. Provider may assign this Agreement without consent.", encoding="utf-8")
    metadata.write_text(
        """
        [
          {
            "file_name": "ACME_01_01_2020-SERVICESAGREEMENT.txt",
            "perturbation": [
              {
                "type": "Structural Flaws - In Text Contradiction",
                "original_text": "Neither party may assign without consent.",
                "changed_text": "Provider may assign this Agreement without consent.",
                "explanation": "The modified text creates one-sided assignment rights.",
                "location": "1"
              }
            ]
          }
        ]
        """,
        encoding="utf-8",
    )

    benchmark = tmp_path / "benchmarks" / "repo_dataset_benchmark.jsonl"
    inventory = tmp_path / "docs" / "DATASET_INVENTORY.md"
    summary = build_repo_dataset_benchmark(benchmark, inventory, root=tmp_path)

    assert summary["benchmark_case_count"] == 1
    assert summary["perturbation_count"] == 1
    line = benchmark.read_text(encoding="utf-8")
    assert "assignment_without_consent" in line
    assert "structural_flaw" in line
    assert "Perturbation records" in inventory.read_text(encoding="utf-8")
