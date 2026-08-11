# ClauseGuard Analysis Report

**Document:** SERVICE AGREEMENT
**Type:** Service Agreement

## Summary

Analyzed 4 clauses and accepted 3 evidence-backed findings (2 high severity).

## Findings

### HIGH: missing_governing_law

- Clause: Document-level
- Rule: `missing_governing_law`
- Decision score: 0.69 (threshold 0.55)
- Primary model confidence: 0.85
- Verifier: not run (neutral confidence 0.50)
- Signals: None
- Explanation: No governing law or venue clause was detected, making dispute forum and applicable law unclear.
- Evidence: Governing Law Checklist, Balanced Discretion Checklist, Confidentiality Checklist

### MEDIUM: risky_language

- Clause: Termination
- Rule: `contextual_risky_language`
- Decision score: 0.65 (threshold 0.62)
- Primary model confidence: 0.80
- Verifier: not run (neutral confidence 0.50)
- Signals: sole discretion
- Explanation: Clause contains broad or one-sided risk terms without enough balancing safeguards: sole discretion.
- Evidence: Balanced Discretion Checklist, Termination Checklist, Data Protection Checklist

Suggested rewrite:

> Provider may terminate this Agreement only under objective, documented
> standards and after written notice, subject to any agreed cure period and
> expressly stated immediate-termination events.

### HIGH: uncapped_indemnity

- Clause: Indemnification
- Rule: `broad_indemnity_without_limits`
- Decision score: 0.67 (threshold 0.55)
- Primary model confidence: 0.84
- Verifier: not run (neutral confidence 0.50)
- Signals: None
- Explanation: Indemnity language appears broad and may lack procedural limits or liability caps.
- Evidence: Indemnity Checklist, Limitation of Liability Checklist, Data Protection Checklist

Suggested rewrite:

> Indemnification is limited to third-party claims caused by breach, negligence,
> willful misconduct, or legal violation, subject to prompt notice, defense
> control, reasonable cooperation, and agreed liability caps.

## Limitations

- This system is a legal analysis assistant and not a lawyer replacement.
- Findings require review by a qualified legal professional.
- Coverage depends on the configured rule set, reference corpus, and document quality.
