import os
import sys

from app.agent.conversation import Conversation
from app.config.settings import load_settings
from app.graph.workflow import build_graph, empty_state
from app.llm.client import (
    ModelUnavailable,
    OllamaUnavailable,
    ensure_model,
    make_llm,
    warm_up,
)
from app.speech.speak import deliver, open_voice, print_speech
from app.memory.store import MemoryStore
from app.mcp.calendar import Calendar
from app.mcp.filesystem import Filesystem
from app.mcp.github import GitHub
from app.mcp.playwright_server import PlaywrightBrowser
from app.mcp.web_search import WebSearch


class Session:
    def __init__(self):
        self.settings = load_settings()
        self.conversation = Conversation()
        self.llm_error = ""
        llm = None
        try:
            ensure_model(self.settings)
            warm_up(self.settings)
            llm = make_llm(self.settings)
        except (OllamaUnavailable, ModelUnavailable) as exc:
            self.llm_error = str(exc)
        self.graph = build_graph(
            llm,
            self.conversation,
            self.llm_error,
            browser=(
                PlaywrightBrowser(self.settings)
                if self.settings.playwright_enabled
                else None
            ),
            search=WebSearch(),
            files=Filesystem(self.settings),
            github=GitHub(self.settings),
            calendar=Calendar(self.settings),
            memory=MemoryStore(
                os.path.join(os.path.dirname(__file__), "data", "memory.json")
            ),
        )

    def ask(self, user_input: str) -> dict:
        return self.graph.invoke(empty_state(user_input))


def print_answer(result: dict) -> None:
    print(f"Intent: {result['intent_seconds']:.2f}s")
    print(f"LLM: {result['llm_seconds']:.2f}s")
    print(f"Tool: {result['tool_seconds']:.2f}s")
    print(
        f"Prompt: {result['prompt_chars']} chars, "
        f"{result['prompt_tokens']} tokens"
    )
    print(
        f"Generation: {result['output_tokens']} tokens, "
        f"{result['tokens_per_second']:.1f} tok/s"
    )
    total = (
        result["intent_seconds"]
        + result["llm_seconds"]
        + result["tool_seconds"]
    )
    print(f"Total: {total:.2f}s")


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--text":
        return text_main(sys.argv[2:])
    from app.speech.loop import run

    return run()


def text_main(args: list[str]) -> int:
    session = Session()
    if session.llm_error:
        print(session.llm_error)
        print("Simple commands still work.")

    if args:
        result = session.ask(" ".join(args))
        voice = open_voice(session.settings)
        print_speech(deliver(voice, result["response"]))
        print_answer(result)
        return 0

    print("Type a message. Type exit to quit.")
    voice = open_voice(session.settings)
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_input:
            continue
        try:
            result = session.ask(user_input)
        except Exception as exc:
            print(f"The request failed: {exc}")
            continue
        print_speech(deliver(voice, result["response"]))
        print_answer(result)
        if result["should_exit"]:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
