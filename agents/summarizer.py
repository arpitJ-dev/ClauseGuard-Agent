from agents.utils.groq_client import GroqClient


class SummarizerAgent:
    """Legacy helper for short summaries using the configured Groq key."""

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        memory: bool = False,
        config: dict | None = None,
    ):
        self.model = GroqClient(model_name=model)
        self.memory = memory
        self.config = config or {}

    def summarize(self, text: str) -> str:
        return self.model.query(
            system_prompt=(
                "Summarize the provided legal or business text in 10 to 15 concise lines. "
                "Focus on obligations, risks, parties, dates, and decision-relevant details."
            ),
            prompt=text,
        )

    def stream(self, text: str):
        print(self.summarize(text))
