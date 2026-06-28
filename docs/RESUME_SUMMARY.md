# Resume Summary

## Project Title

ClauseGuard Agent: Agentic Contract Risk Analysis System

## Resume Bullet Options

- Built an agentic legal contract analysis system using Groq-hosted LLM agents, local RAG, structured clause extraction, independent verifier review, weighted evidence scoring, and automated rewrite/report generation.
- Implemented a multi-agent pipeline for document ingestion, clause classification, compliance issue detection, evidence retrieval, verifier agreement, clause rewriting, and Markdown/JSON reporting.
- Designed transparent weighted scoring across deterministic legal checks, retrieved evidence, primary model reasoning, verifier agreement, and clause-structure signals to avoid a simple single-model wrapper.
- Added a benchmark harness that builds a repo-dataset manifest, reports issue-type precision, recall, F1, per-case findings, per-issue metrics, and model usage snapshots.
- Added provider safety controls with model allowlists, request caps, estimated input-token caps, mock-model tests, local embeddings, and no paid vector database or paid web-search dependency.

## Technical Highlights

- Python package with CLI entrypoints: `python -m legal_lm analyze ...` and `python -m legal_lm evaluate ...`
- Supports `.txt`, `.docx`, and `.pdf`
- Uses Pydantic schemas for clauses, evidence, findings, scores, rewrites, and reports
- Local vector retrieval replaces Qdrant Cloud in the default path
- Mock mode supports recruiter demos without API keys or quota usage
- Current validation: 24 passing tests, compile checks, real Groq smoke test, and three end-to-end sample reports
- Current evaluation status: seed benchmark has 3 labeled cases with mock/local precision, recall, and F1 of `1.0000`; repo perturbation benchmark has 11 cases from 31 perturbation records with precision `0.6154`, recall `0.8000`, and F1 `0.6957`

## Honest Positioning

This is a resume-ready prototype, not a production legal product. The benchmark metrics are for mapped issue labels, not broad legal accuracy. It demonstrates applied LLM engineering, agent orchestration, RAG, verifier patterns, scoring design, dataset-backed benchmark reporting, and practical API safety.
