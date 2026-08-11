# Security Policy

## Reporting a Vulnerability

Use a private GitHub Security Advisory for suspected credential exposure,
dependency vulnerabilities, unsafe document handling, or prompt-injection paths.
Do not disclose exploitable details in a public issue before a fix is available.

## Credential Handling

- Credentials are loaded from the process environment or an ignored `.env` file.
- `.env.example` contains placeholders only.
- Logs and reports must never include authorization headers or credential values.
- Rotate a credential immediately if it is committed, pasted into an issue, or
  exposed in terminal output.

The publish-readiness script scans maintained text files for common provider-key
formats. This is a guardrail, not a replacement for repository secret scanning.

## Contract Data

Hosted analysis sends relevant contract text to the configured model provider.
Do not process privileged, confidential, personal, export-controlled, or otherwise
restricted material unless the provider, account configuration, and organizational
policy explicitly permit it.

The deterministic test and benchmark workflows operate on bundled public or
synthetic fixtures. Generated reports are ignored by default because they may
contain source contract language.

## Untrusted Input

Contracts are treated as untrusted data rather than instructions. Model prompts
separate system policy from serialized document content, and model output is
validated before entering application state. Consumers should still review output
for prompt injection, fabricated authority, and adversarial formatting.

## Output Integrity

ClauseGuard is a review aid, not an authorization or enforcement system. Do not
automatically execute contractual decisions from a finding or rewrite. Preserve
the source document, JSON audit record, model configuration, and human approval
when findings influence a legal workflow.

## Dependency Hygiene

CI installs dependencies from `pyproject.toml`, runs static analysis and tests,
and exercises parsers with malformed inputs. Review dependency updates before
merging, especially document parsers and network clients.
