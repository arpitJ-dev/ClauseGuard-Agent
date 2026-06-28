# Dataset Inventory

This inventory is generated from the repo's local contract perturbation dataset.

## Summary

| Metric | Value |
|---|---:|
| Original text files | 12 |
| Modified files | 12 |
| Perturbation JSON files | 11 |
| Perturbation records | 31 |
| Benchmark cases generated | 11 |
| Skipped records | 0 |

Benchmark manifest: `benchmarks/repo_dataset_benchmark.jsonl`

## Perturbation Types

| Type | Count |
|---|---:|
| Ambiguities - Ambiguous Legal Obligation | 3 |
| Ambiguities - In Text Contradiction | 3 |
| Inconsistencies - In Text Contradiction | 3 |
| Inconsistencies - Legal Contradiction | 3 |
| Misaligned Terminology - In Text Contradiction | 3 |
| Misaligned Terminology - Legal Contradiction | 3 |
| Omissions - In Text Contradiction | 3 |
| Omissions - Omission Legal Contradiction | 4 |
| Structural Flaws - In Text Contradiction | 3 |
| Structural Flaws - Legal Contradiction | 3 |

## Expected Issue Labels

| Issue Type | Count |
|---|---:|
| internal_contradiction | 28 |
| misaligned_terminology | 6 |
| missing_required_language | 7 |
| risky_language | 7 |
| structural_flaw | 6 |

## Notes

- Labels are mapped from perturbation metadata into the current ClauseGuard Agent issue taxonomy.
- Metrics from this dataset measure the current system against these mapped labels; they are not broad legal accuracy.
- The benchmark can be run locally without API quota using `python -m legal_lm evaluate benchmarks\repo_dataset_benchmark.jsonl --mock-models`.
