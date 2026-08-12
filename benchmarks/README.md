# Evaluation Benchmarks

ClauseGuard includes two versioned, reproducible issue-classification suites.

| Manifest | Purpose | Cases |
|---|---|---:|
| `seed_contracts.jsonl` | Focused positive and negative regression fixtures | 3 |
| `repo_dataset_benchmark.jsonl` | Contract perturbations derived from the bundled dataset | 11 |

## Case Schema

Each JSONL record defines:

- a stable case ID;
- the contract supplied to the standalone analysis pipeline;
- expected issue types;
- optional explicitly absent issue types;
- provenance linking the source contract and perturbation metadata;
- structured perturbation summaries for error analysis.

## Methodology

Evaluation occurs at the case-level issue-type boundary. A predicted issue type is
counted once per document, even if multiple clauses produce that issue. Aggregate
precision, recall, and F1 are computed from the summed true-positive,
false-positive, and false-negative counts.

The perturbation suite uses only modified contracts as prediction input. Original
contracts and change metadata are retained for label provenance and the separate
comparison workflow. This prevents paired-document text from leaking into the
standalone detector.

Issue types outside a manifest's mapped taxonomy are retained in the report for
manual analysis and are not mixed into that benchmark's classification matrix.
Per-case and per-issue tables make this scope visible.

## Reproduce

```bash
clauseguard evaluate benchmarks/seed_contracts.jsonl --mock-models
clauseguard build-dataset-benchmark
clauseguard evaluate benchmarks/repo_dataset_benchmark.jsonl --mock-models
```

Results include Markdown and JSON summaries plus the full analysis report for
every case. See `data/README.md` for dataset layout, provenance, and usage notes.
The upstream attribution and redistribution notice is in `data/NOTICE.md`.
