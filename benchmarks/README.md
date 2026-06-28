# Benchmark Fixtures

This directory contains the first local benchmark set for Legal-LLM evaluation.

The JSONL file labels expected issue types for small contract excerpts. Running the benchmark in mock/local mode does not call Groq:

```bash
python -m legal_lm evaluate benchmarks\seed_contracts.jsonl --mock-models
```

Real-model evaluation is intentionally opt-in and capped to one case by default:

```bash
python -m legal_lm evaluate benchmarks\seed_contracts.jsonl --real-models --max-cases 1
```

These fixtures measure issue-type detection for the current rule and agent workflow. They are not a substitute for a larger CLAUSE, CUAD, or ContractNLI-style evaluation set.
