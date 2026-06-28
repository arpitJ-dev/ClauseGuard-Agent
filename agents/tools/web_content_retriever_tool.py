from pydantic import BaseModel, Field
from typing import Optional

from langchain_core.tools import BaseTool
from langchain_core.tools.base import ArgsSchema

class WebContentRetrieverToolInput(BaseModel):
    query: str = Field(description="Input Query to search.")

class WebContentRetrieverTool(BaseTool):
    name: str = "web_content_retriever"
    description: str = "Archived legacy web retriever. The v1 pipeline uses legal_lm.rag local retrieval."
    args_schema: Optional[ArgsSchema] = WebContentRetrieverToolInput

    def _run(self, query: str):
        raise RuntimeError(
            "Legacy web retrieval is archived. The current v1 path uses legal_lm.rag local retrieval."
        )
    
####################################################################
# USAGE GUIDE
####################################################################
# memory = MemorySaver()
# llm = GroqClient(model_name="llama-3.3-70b-versatile")

# web_content_tool = WebContentRetrieverTool()
# tools = [web_content_tool]

# agent_executor = create_react_agent(model=llm, tools=tools, checkpointer=memory)

# config = {"configurable": {"thread_id": "abc123"}}
# for step in agent_executor.stream(
#     {"messages": [HumanMessage(content="Is langchain the best tool in the market ?")]},
#     config,
#     stream_mode="values",
# ):
#     step["messages"][-1].pretty_print()
