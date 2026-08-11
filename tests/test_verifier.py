from clauseguard.agents.verifier import VerifierAgent
from clauseguard.config import AppConfig
from clauseguard.model_router import ModelRouter
from clauseguard.schemas import CandidateFinding


def _candidate() -> CandidateFinding:
    return CandidateFinding(
        id="finding-1",
        issue_type="missing_termination",
        severity="MEDIUM",
        explanation="No termination clause was detected.",
        deterministic_score=0.8,
        structure_score=0.8,
    )


def test_mock_verifier_reports_not_run_with_neutral_score():
    verifier = VerifierAgent(ModelRouter(AppConfig(groq_api_key=None, mock_models=True)))

    result = verifier.verify([_candidate()])

    assert result[0].verifier_status == "not_run"
    assert result[0].verifier_confidence == 0.5
    assert "neutral score" in result[0].verifier_rationale


def test_verifier_marks_structured_response_as_verified(monkeypatch):
    router = ModelRouter(AppConfig(groq_api_key="groq-key", mock_models=False))
    monkeypatch.setattr(
        router,
        "generate_json",
        lambda *args, **kwargs: {
            "verifications": [
                {
                    "id": "finding-1",
                    "agreement": 0.9,
                    "confidence": 0.8,
                    "rationale": "The clause inventory supports the finding.",
                }
            ]
        },
    )

    result = VerifierAgent(router).verify([_candidate()])

    assert result[0].verifier_status == "verified"
    assert result[0].verifier_confidence == 0.85
    assert result[0].verifier_rationale.startswith("The clause inventory")
