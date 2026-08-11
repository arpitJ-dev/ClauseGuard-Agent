from clauseguard.agents.compliance import ComplianceCheckerAgent
from clauseguard.config import AppConfig
from clauseguard.context import ContextBank
from clauseguard.model_router import ModelRouter
from clauseguard.schemas import Clause


def _agent() -> ComplianceCheckerAgent:
    return ComplianceCheckerAgent(ModelRouter(AppConfig(groq_api_key=None, mock_models=True)))


def _context(*clauses: Clause, document_type: str = "Commercial Agreement") -> ContextBank:
    context = ContextBank(document_id="doc-test")
    context.document_type = document_type
    context.clauses = list(clauses)
    return context


def test_incomplete_governing_law_detects_arbitration_without_law_standard():
    clause = Clause(
        id="clause-001",
        order=1,
        title="Governing Law",
        category="Governing Law",
        text=(
            "8.05 GOVERNING LAW. All disputes or claims hereunder shall be resolved "
            "by arbitration in McLean, Virginia, pursuant to the rules of the American Arbitration Association."
        ),
    )

    findings = _agent()._missing_required_language_findings(_context(clause))

    assert any(finding.issue_type == "missing_required_language" for finding in findings)
    assert any(finding.rule_id == "incomplete_governing_law_clause" for finding in findings)


def test_complete_governing_law_is_not_missing_required_language():
    clause = Clause(
        id="clause-001",
        order=1,
        title="Governing Law",
        category="Governing Law",
        text=(
            "7.2 Governing Law. This Agreement and all disputes are governed by "
            "and construed in accordance with the laws of the State of New York."
        ),
    )

    findings = _agent()._missing_required_language_findings(_context(clause))

    assert not findings


def test_benign_notwithstanding_and_however_recorded_do_not_trigger_contradiction():
    agent = _agent()
    service_clause = (
        "Notwithstanding the contents of the Exhibit, Provider agrees to respond in good faith "
        "to any reasonable request by Recipient for access to additional services."
    )
    confidentiality_clause = (
        "Confidential Information means information however recorded or preserved. "
        'Notwithstanding the foregoing, "Confidential Information" shall not include public information.'
    )

    assert not agent._has_internal_contradiction_markers(service_clause.lower())
    assert not agent._has_internal_contradiction_markers(confidentiality_clause.lower())


def test_high_signal_notwithstanding_still_triggers_contradiction():
    clause_text = (
        "Notwithstanding any other paragraph of this Agreement, Provider may terminate "
        "this agreement on written notice and Customer shall not be entitled to further service credits."
    )

    assert _agent()._has_internal_contradiction_markers(clause_text.lower())


def test_contextual_risky_language_requires_unbalanced_context():
    agent = _agent()
    balanced = Clause(
        id="clause-001",
        order=1,
        title="Service Levels",
        category="General",
        text="Provider shall perform services satisfactory to Customer in good faith and in a commercially reasonable manner.",
        risk_terms=[],
    )
    unbalanced = Clause(
        id="clause-002",
        order=2,
        title="Returns",
        category="General",
        text="Provider may reject returns in its sole discretion and all products are sold as is.",
        risk_terms=["sole discretion", "as is"],
    )

    assert agent._risky_language_signal(balanced, balanced.text.lower()) is None
    assert agent._risky_language_signal(unbalanced, unbalanced.text.lower()) is not None
