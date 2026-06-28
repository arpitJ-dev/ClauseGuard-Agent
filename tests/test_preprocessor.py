from legal_lm.config import AppConfig
from legal_lm.model_router import ModelRouter
from legal_lm.agents.preprocessor import PreprocessorAgent
from legal_lm.schemas import Clause, LoadedDocument


def test_preprocessor_extracts_clauses_and_entities():
    router = ModelRouter(
        AppConfig(
            groq_api_key=None,
            mock_models=True,
        )
    )
    document = LoadedDocument(
        path="sample.txt",
        file_type="txt",
        title="SERVICES AGREEMENT",
        text=(
            "SERVICES AGREEMENT\n\n"
            "1. Payment. Acme Inc. shall pay $10,000 within 30 days.\n\n"
            "2. Governing Law. This agreement is governed by the laws of California."
        ),
    )

    document_type, clauses, entities = PreprocessorAgent(router).process(document)

    assert document_type == "Service Agreement"
    assert len(clauses) == 2
    assert any(entity.label == "MONEY" for entity in entities)
    assert any(clause.category == "Governing Law" for clause in clauses)


def test_preprocessor_keeps_deterministic_clauses_when_model_output_is_partial():
    router = ModelRouter(AppConfig(groq_api_key=None, mock_models=True))
    agent = PreprocessorAgent(router)
    deterministic = [
        Clause(id=f"clause-{index:03d}", order=index, title=f"Clause {index}", text="x" * 80)
        for index in range(1, 5)
    ]
    model = [Clause(id="clause-001", order=1, title="Summary", text="x" * 80)]

    selected = agent._select_clause_set(deterministic, model)

    assert selected == deterministic


def test_preprocessor_detects_laws_of_as_governing_law():
    router = ModelRouter(AppConfig(groq_api_key=None, mock_models=True))
    agent = PreprocessorAgent(router)

    assert agent._categorize("This agreement is governed by the laws of Pennsylvania.") == "Governing Law"
