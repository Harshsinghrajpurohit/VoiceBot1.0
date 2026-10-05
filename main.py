import sys

from app.config.settings import load_settings
from app.graph.workflow import build_graph
from app.llm.client import (
    ModelUnavailable,
    OllamaUnavailable,
    ensure_model,
    make_llm,
)


class Session:
    def __init__(self):
        self.settings = load_settings()
        ensure_model(self.settings)
        self.graph = build_graph(make_llm(self.settings))

    def ask(self, user_input: str) -> tuple[str, float]:
        result = self.graph.invoke(
            {
                "user_input": user_input,
                "response": "",
                "llm_seconds": 0.0,
            }
        )
        return result["response"], result["llm_seconds"]


def print_answer(session: Session, user_input: str) -> None:
    try:
        text, seconds = session.ask(user_input)
    except Exception as exc:
        print(f"The model request failed: {exc}")
        return
    print(text)
    print(f"LLM: {seconds:.2f}s")
    print(f"Total: {seconds:.2f}s")


def main() -> int:
    try:
        session = Session()
    except (OllamaUnavailable, ModelUnavailable) as exc:
        print(exc)
        return 1

    if len(sys.argv) > 1:
        print_answer(session, " ".join(sys.argv[1:]))
        return 0

    print("Type a message. Type exit to quit.")
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            return 0
        print_answer(session, user_input)


if __name__ == "__main__":
    raise SystemExit(main())
