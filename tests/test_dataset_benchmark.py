from pathlib import Path

from clauseguard.dataset_benchmark import build_repo_dataset_benchmark


def test_build_repo_dataset_benchmark_pairs_modified_file_and_maps_labels(tmp_path: Path):
    originals = tmp_path / "data" / "original"
    perturbations = tmp_path / "data" / "perturbations"
    originals.mkdir(parents=True)
    perturbations.mkdir(parents=True)

    original = originals / "ACME_01_01_2020-SERVICESAGREEMENT.txt"
    modified = perturbations / "modified_ACME_01_01_2020-SERVICESAGREEMENT.txt.txt"
    metadata = perturbations / "perturbed_ACME_01_01_2020-SERVICESAGREEMENT.txt.json"

    original.write_text(
        "SERVICES AGREEMENT\n\n1. Assignment. Neither party may assign without consent.",
        encoding="utf-8",
    )
    modified.write_text(
        "SERVICES AGREEMENT\n\n1. Assignment. Provider may assign this Agreement without consent.",
        encoding="utf-8",
    )
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
    assert "internal_contradiction" in line
    assert "structural_flaw" not in line
    assert "Perturbation records" in inventory.read_text(encoding="utf-8")


def test_structural_placement_perturbation_maps_to_structural_flaw(tmp_path: Path):
    originals = tmp_path / "data" / "original"
    perturbations = tmp_path / "data" / "perturbations"
    originals.mkdir(parents=True)
    perturbations.mkdir(parents=True)

    source_name = "ACME-SUPPLY-AGREEMENT.txt"
    (originals / source_name).write_text(
        "SUPPLY AGREEMENT\n\n14. Warranty. Supplier warrants the goods.",
        encoding="utf-8",
    )
    (perturbations / f"modified_{source_name}.txt").write_text(
        "SUPPLY AGREEMENT\n\n21. Miscellaneous. 14.1 Supplier warrants the goods.",
        encoding="utf-8",
    )
    (perturbations / f"perturbed_{source_name}.json").write_text(
        """
        [{
          "file_name": "ACME-SUPPLY-AGREEMENT.txt",
          "perturbation": [{
            "type": "Structural Flaws - Legal Contradiction",
            "original_text": "14. Warranty.",
            "changed_text": "21. Miscellaneous. 14.1 Warranty.",
            "explanation": "The warranty was moved beneath an unrelated heading.",
            "location": "Section 14 to Section 21"
          }]
        }]
        """,
        encoding="utf-8",
    )

    benchmark = tmp_path / "benchmark.jsonl"
    build_repo_dataset_benchmark(benchmark, tmp_path / "inventory.md", root=tmp_path)

    assert "structural_flaw" in benchmark.read_text(encoding="utf-8")
