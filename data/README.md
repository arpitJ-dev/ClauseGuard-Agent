# Evaluation Data

This directory contains the contract sources and synthetic perturbations used by
ClauseGuard's repository regression benchmark.

## Layout

- `original/` contains ten source contract exhibits.
- `perturbations/` contains modified contracts and structured change metadata.
- `paired_example/` contains one additional original/modified pair in multiple
  document formats.

Source filenames retain registrant, filing date, filing form, exhibit number,
and agreement type where that information was present in the supplied corpus.
Perturbation JSON records preserve the original text, changed text, issue family,
explanation, and source location used to derive benchmark labels.

The original agreement is never supplied to the standalone detection pipeline.
It is retained for provenance and for the separate comparison command. Benchmark
predictions are made from each modified agreement alone.

The `contradicted_law` text in perturbation metadata is source annotation, not a
ClauseGuard legal authority. The active retrieval corpus uses curated review
checklists, and generated findings still require professional legal review.

The MIT license covers the project source code. Contract exhibits and derived
dataset records retain their underlying source considerations; verify applicable
source terms before redistributing the dataset independently.
