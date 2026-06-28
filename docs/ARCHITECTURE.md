# Architecture

ClauseGuard Agent is a command-line, agentic contract analysis prototype. It uses Groq-hosted language models for generation, local deterministic retrieval, and transparent scoring.

## Pipeline

```text
Document Input
  -> Preprocessor Agent
  -> Context Bank
  -> Knowledge Agent / Local RAG
  -> Compliance Checker
  -> Groq Verifier
  -> Weighted Scoring
  -> Clause Rewriter
  -> Postprocessor
  -> Benchmark Evaluator
```

## Components

- **Document Loader:** reads `.txt`, `.docx`, and `.pdf` files while preserving clause order as much as possible.
- **Preprocessor Agent:** classifies the contract, extracts clauses, identifies basic entities, and tags risk terms.
- **Context Bank:** stores a normalized single-document analysis state for all agents.
- **Knowledge Agent:** uses a local vector store over built-in legal checklist references. Qdrant Cloud and paid web search are not used in the v1 default path.
- **Compliance Checker:** creates candidate findings for missing clauses, risky language, broad indemnity, vague payment terms, assignment risk, termination risk, internal contradictions, structural flaws, and terminology drift.
- **Verifier Agent:** sends candidate findings to Groq for independent review.
- **Weighted Scoring:** combines deterministic rules, local evidence, primary model reasoning, verifier agreement, and clause structure into one final confidence score.
- **Clause Rewriter:** drafts safer clause alternatives for accepted clause-level findings.
- **Postprocessor:** writes JSON and Markdown reports.
- **Benchmark Evaluator:** runs labeled benchmark cases, compares accepted issue types against expected labels, and reports precision, recall, F1, and usage snapshots.

## Model Roles

| Role | Provider | Default Model | Purpose |
|---|---|---|---|
| Extraction | Groq | `llama-3.1-8b-instant` | Clause extraction and JSON normalization |
| Embedding | Local | `local-hash-lexical` | Deterministic local RAG retrieval |
| Reasoning | Groq | `llama-3.3-70b-versatile` | Compliance reasoning and rewrites |
| Verifier | Groq | `openai/gpt-oss-120b` | Independent verifier |

## Scoring

```text
deterministic legal/rule checks       30%
retrieved evidence/RAG match          25%
primary model reasoning               20%
verifier agreement                    15%
clause structure/consistency          10%
```

This is evidence-weighted decision scoring, not model fine-tuning. The project does not train or modify model weights.

## Safety Boundaries

- `FREE_TIER_ONLY=true` blocks non-approved model configuration.
- Per-run request and estimated input-token caps stop runaway quota use. Match caps to the account limits shown in the Groq console.
- Benchmark evaluation defaults to mock/local mode. Real Groq evaluation is explicit and capped to one case by default.
- `.env` is ignored and `.env.example` contains placeholders only.
- The v1 system is not legal advice and should not be used as a production legal product.

## Evaluation

The project includes a small seed benchmark and a repo-dataset benchmark built from the included original/modified perturbation files:

```bash
python -m legal_lm evaluate benchmarks\seed_contracts.jsonl --mock-models
python -m legal_lm build-dataset-benchmark
python -m legal_lm evaluate benchmarks\repo_dataset_benchmark.jsonl --mock-models
```

Current local results:

| Benchmark | Cases | Precision | Recall | F1 | API Calls |
|---|---:|---:|---:|---:|---:|
| Seed benchmark | 3 | `1.0000` | `1.0000` | `1.0000` | 0 |
| Repo perturbation dataset | 11 | `0.6154` | `0.8000` | `0.6957` | 0 |

The repo dataset contains 31 perturbation records mapped into the current issue taxonomy. These metrics should be treated as benchmark progress indicators, not broad legal accuracy.
