# Legal-LLM Analysis Report

**Document:** SERVICE AGREEMENT
**Type:** SERVICE AGREEMENT

## Summary

Analyzed 4 clauses and accepted 3 evidence-backed findings.

## Findings

### HIGH: missing_governing_law

- Clause: Document-level
- Final score: 0.77
- Primary model confidence: 0.90
- Verifier confidence: 0.85
- Explanation: No governing law or venue clause was detected, making dispute forum and applicable law unclear.
- Evidence: Confidentiality Checklist, Data Protection Checklist, Indemnity Checklist

### MEDIUM: risky_language

- Clause: Termination
- Final score: 0.68
- Primary model confidence: 0.90
- Verifier confidence: 0.75
- Explanation: Clause contains broad or one-sided risk terms: sole discretion.
- Evidence: Termination Checklist, Assignment Checklist

Suggested rewrite:

Provider may terminate this Agreement without cause by giving written notice.

### HIGH: uncapped_indemnity

- Clause: Indemnification
- Final score: 0.76
- Primary model confidence: 0.85
- Verifier confidence: 0.93
- Explanation: Indemnity language appears broad and may lack procedural limits or liability caps.
- Evidence: Indemnity Checklist, Limitation of Liability Checklist

Suggested rewrite:

Customer shall indemnify Provider from third-party claims, provided that Provider promptly notifies Customer, grants Customer control over the defense and settlement, and Customer's aggregate indemnification liability is capped at an agreed amount.

## Limitations

- This system is a legal analysis assistant and not a lawyer replacement.
- Findings require review by a qualified legal professional.
- External model APIs may throttle or fail when quota is exhausted.
