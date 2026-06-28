# GitHub Release Checklist

Use this checklist before publishing the project under your job-application GitHub account.

## Required

- Rotate all Groq, Qdrant, Tavily, or other API keys that were ever stored locally.
- Confirm `.env` is not committed.
- Read `SECURITY.md`.
- Run `python scripts/check_publish_ready.py`.
- Run `python -m pytest -q`.
- Run `python -m compileall legal_lm agents context_bank.py`.
- Run a no-quota demo:

```bash
python -m legal_lm analyze examples\demo_contract.txt --mock-models
```

- Rebuild and run the local dataset benchmark:

```bash
python -m legal_lm build-dataset-benchmark
python -m legal_lm evaluate benchmarks\repo_dataset_benchmark.jsonl --mock-models
```

- Optional: run a small real Groq smoke test after confirming account limits:

```bash
python scripts\smoke_groq.py
```

- Confirm `README.md`, `.env.example`, `docs/ARCHITECTURE.md`, and `examples/sample_report.md` render correctly on GitHub.

## Recommended

- Choose a license before making the repository public.
- Keep generated outputs under ignored folders such as `analysis_outputs/` and `test_outputs/`.
- Do not publish notebook outputs unless reviewed for credentials and private data.
- Keep `Original_files/`, `Perturbations/`, and other datasets only if their usage rights are acceptable for public portfolio work.
- Add screenshots or a short demo GIF only after the repo is cleaned.

## Suggested Repository Description

Agentic legal contract analysis prototype using Groq-hosted LLM agents, local RAG, weighted evidence scoring, verifier review, and automated clause rewrite reports.
