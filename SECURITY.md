# Security

## API Keys

Never commit API keys or provider tokens. The project reads credentials from `.env`, and `.env` is ignored by default.

Before publishing this repository, rotate any key that was ever stored locally during development, including:

- Groq API keys
- Qdrant API keys
- Tavily API keys
- Any OpenAI or other LLM provider keys

## Legal Documents

Do not submit confidential, privileged, or private legal documents to external cloud models. Use public contracts, synthetic examples, or approved benchmark data.

## Cost Controls

The project defaults to `FREE_TIER_ONLY=true` and enforces per-run request and estimated input-token caps. Match local caps to your Groq console limits before running real model-backed demos, and do not disable these controls for portfolio demos.

## Reporting Issues

For a private portfolio repository, track security issues privately until credentials and sensitive data have been reviewed.
