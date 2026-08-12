# Dataset Inventory

This inventory is generated from the repo's local contract perturbation dataset.

The files are an 11-case regression subset of the CLAUSE benchmark published with
Choudhury et al. (EACL 2026). See [`data/NOTICE.md`](../data/NOTICE.md) for source,
licensing, and citation details.

## Summary

| Metric | Value |
|---|---:|
| Original text files | 11 |
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

## Perturbation-Level Label Mappings

| Issue Type | Mapped perturbations |
|---|---:|
| internal_contradiction | 28 |
| misaligned_terminology | 6 |
| missing_required_language | 7 |
| risky_language | 7 |
| structural_flaw | 3 |

## Notes

- Labels are mapped from perturbation metadata into the current ClauseGuard issue taxonomy.
- Mapping counts above are perturbation-level; benchmark metrics deduplicate labels at the case level.
- Evaluation uses case-level issue labels mapped from the perturbation metadata.
- Only modified contracts are passed to the detection pipeline; original documents remain provenance for the labels.
- The manifest retains source paths and changed-text previews for reproducible error analysis.
- Counts describe the bundled subset, not the complete upstream CLAUSE corpus.
