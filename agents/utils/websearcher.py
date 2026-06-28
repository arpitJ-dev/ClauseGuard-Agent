class WebContentRetriever:
    """Archived legacy web retriever.

    The production-style v1 pipeline uses ``legal_lm.rag.KnowledgeAgent`` with
    local references. This placeholder prevents accidental web/Qdrant/local
    model usage from old experimental code paths.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Legacy web retrieval is archived. Use legal_lm.rag.KnowledgeAgent "
            "for the current local retrieval path."
        )
