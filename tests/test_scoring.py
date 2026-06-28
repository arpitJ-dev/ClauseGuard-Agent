from legal_lm.scoring import WEIGHTS, WeightedScorer


def test_weighted_scoring_uses_expected_weights():
    scores = WeightedScorer().score(
        deterministic_rules=1.0,
        rag_evidence=0.5,
        primary_reasoning=0.5,
        verifier_agreement=0.5,
        clause_structure=0.5,
    )

    expected = 1.0 * WEIGHTS["deterministic_rules"]
    expected += 0.5 * (
        WEIGHTS["rag_evidence"]
        + WEIGHTS["primary_reasoning"]
        + WEIGHTS["verifier_agreement"]
        + WEIGHTS["clause_structure"]
    )
    assert scores.final == round(expected, 4)
    assert WeightedScorer().is_accepted(scores)


def test_structural_flaw_uses_stricter_acceptance_threshold():
    scores = WeightedScorer().score(
        deterministic_rules=0.68,
        rag_evidence=0.20,
        primary_reasoning=0.68,
        verifier_agreement=0.58,
        clause_structure=0.82,
    )

    assert scores.final < 0.60
    assert WeightedScorer().is_accepted(scores)
    assert not WeightedScorer().is_accepted(scores, "structural_flaw")
