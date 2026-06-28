from agents.utils.response_parser import ResponseParser


def test_response_parser_accepts_inline_field_values():
    response = """
    [ISSUE]
    Description: Missing governing law.
    Severity: HIGH
    References: Governing law checklist
    Reasoning: The contract does not say which law applies.
    [/ISSUE]
    """

    issues = ResponseParser().parse_issues(response)

    assert len(issues) == 1
    assert issues[0]["description"] == "Missing governing law."
    assert issues[0]["severity"] == "HIGH"
