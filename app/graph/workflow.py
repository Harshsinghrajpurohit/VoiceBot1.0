import time
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

SYSTEM_PROMPT = (
    "You are a local voice assistant. "
    "Answer in one or two short sentences."
)


class TurnState(TypedDict):
    user_input: str
    response: str
    llm_seconds: float


def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def build_graph(llm):
    def generate(state: TurnState) -> dict:
        started = time.perf_counter()
        message = llm.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=state["user_input"]),
            ]
        )
        elapsed = time.perf_counter() - started
        return {
            "response": message_text(message),
            "llm_seconds": elapsed,
        }

    graph = StateGraph(TurnState)
    graph.add_node("generate", generate)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    return graph.compile()
