import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from app.mcp.playwright_server import ALLOW, needs_browser, resolve_page, trim_page
from app.mcp.calendar import MISSING as CALENDAR_MISSING
from app.mcp.calendar import UNAVAILABLE as CALENDAR_UNAVAILABLE
from app.mcp.calendar import calendar_request, events_from_tool_text
from app.mcp.github import github_request
from app.mcp.filesystem import (
    REFUSED,
    UNAVAILABLE,
    UNSEEN,
    filesystem_request,
)
from app.mcp.web_search import search_query
from langgraph.graph import END, START, StateGraph

from app.agent.conversation import Conversation
from app.agent.intent import detect_intent
from app.measure.usage import generation_stats, prompt_chars
from app.tools.calculator import calculate, needs_calculator
from app.tools.clock import current_date, current_time

SYSTEM_PROMPT = (
    "You are a local voice assistant. "
    "Answer in one or two short sentences. "
    "Answer facts, places, and conversation yourself. "
    "Call the calculator tool only for arithmetic, such as 17 * 23."
)


class TurnState(TypedDict):
    user_input: str
    response: str
    route: str
    intent: str
    intent_seconds: float
    llm_seconds: float
    tool_seconds: float
    load_seconds: float
    prompt_chars: int
    prompt_tokens: int
    output_tokens: int
    tokens_per_second: float
    tool_name: str
    tool_args: dict
    tool_calls: list
    should_exit: bool


_CALCULATOR_EXPRESSION = re.compile(
    r"(?P<expression>\d[\d\s()+\-*/%.]*\d|\d)",
)


def _split_requests(text: str) -> list[str]:
    """Split on 'and then' / 'and' / ';' so each part maps to one tool."""
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = re.split(r"\s*(?:and then|then|;\s*|\sand\s)\s*", cleaned, flags=re.IGNORECASE)
    return [part.strip().rstrip("?.!").strip() for part in parts if part.strip()]


def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def expression_from_text(text: str) -> str:
    """Read an expression when the model writes a calculator call as text."""
    if "calculator" not in text.lower():
        return ""
    marker = '"expression"'
    start = text.find(marker)
    if start < 0:
        return ""
    quote = text.find('"', start + len(marker))
    if quote < 0:
        return ""
    end = text.find('"', quote + 1)
    if end < 0:
        return ""
    return text[quote + 1 : end].strip()


def empty_state(user_input: str) -> TurnState:
    return {
        "user_input": user_input,
        "response": "",
        "route": "",
        "intent": "",
        "intent_seconds": 0.0,
        "llm_seconds": 0.0,
        "tool_seconds": 0.0,
        "load_seconds": 0.0,
        "prompt_chars": 0,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "tokens_per_second": 0.0,
        "tool_name": "",
        "tool_args": {},
        "tool_calls": [],
        "should_exit": False,
    }


@tool
def calculator(expression: str) -> str:
    """Evaluate one arithmetic expression. Example: 17 * 23."""
    return calculate(expression)


@tool
def browser_navigate(url: str) -> str:
    """Open one http or https page."""
    return url


@tool
def browser_snapshot() -> str:
    """Read the open page as text."""
    return ""


def build_graph(
    llm,
    conversation: Conversation | None = None,
    llm_error: str = "",
    browser=None,
    search=None,
    files=None,
    github=None,
    calendar=None,
    memory=None,
):
    if conversation is None:
        conversation = Conversation()

    model = None
    tooled = None
    browser_model = None
    if llm is not None:
        model = llm
        tooled = llm.bind_tools([calculator])
        if browser is not None:
            browser_model = llm.bind_tools([browser_navigate, browser_snapshot])

    def route(state: TurnState) -> dict:
        started = time.perf_counter()
        intent = detect_intent(state["user_input"])
        elapsed = time.perf_counter() - started
        path = "fast" if intent else "agent"
        return {
            "intent": intent,
            "route": path,
            "intent_seconds": elapsed,
        }

    def fast(state: TurnState) -> dict:
        intent = state["intent"]
        should_exit = False
        if intent == "time":
            text = current_time()
        elif intent == "date":
            text = current_date()
        elif intent in {"stop", "cancel"}:
            text = "Okay, stopped."
        elif intent == "repeat":
            text = conversation.last_response or "I have nothing to repeat."
        elif intent == "clear":
            conversation.clear()
            text = "Conversation cleared."
        elif intent == "exit":
            text = "Goodbye."
            should_exit = True
        else:
            text = "I can't do that directly."
        if intent not in {"clear", "exit"}:
            conversation.add(state["user_input"], text)
        return {
            "response": text,
            "should_exit": should_exit,
            "llm_seconds": 0.0,
            "tool_seconds": 0.0,
            "load_seconds": 0.0,
            "prompt_chars": 0,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "tokens_per_second": 0.0,
            "tool_name": "",
        }

    def plan_part(part: str) -> tuple[str, dict, str]:
        """Map one independent part to one tool call. Empty name = no tool."""
        if github is not None:
            action, github_args = github_request(part)
            if action:
                return action, github_args, "github"
        if calendar is not None:
            action, calendar_args = calendar_request(part)
            if action:
                return action, calendar_args, "calendar"
        if files is not None:
            kind, file_args = filesystem_request(part, files.roots())
            if kind == "refused":
                return "refused", {}, "files"
            if kind == "missing":
                return "missing", {}, "files"
            if kind:
                return kind, file_args, "files"
        if search is not None and not needs_calculator(part):
            query = search_query(part)
            if query:
                return "web_search", {"query": query}, "search"
        page_url = resolve_page(part) if browser is not None else ""
        if page_url:
            return "browser_navigate", {"url": page_url}, "browser"
        return "", {}, ""

    def plan_deterministic(user_text: str) -> list[dict]:
        """Plan 2+ tools from different sources without a model call.

        Single-tool requests keep their existing path so the model still
        chooses calculator/browser expressions. This only fires when two
        or more independent parts map to different sources.
        """
        parts = _split_requests(user_text)
        if len(parts) < 2:
            return []
        calls = []
        sources = set()
        for part in parts:
            name, args, source = plan_part(part)
            if name in {"refused", "missing"}:
                return []
            if name:
                sources.add(source or name)
                calls.append({"name": name, "args": args, "part": part})
        seen = set()
        unique = []
        for call in calls:
            key = (call["name"], json.dumps(call["args"], sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique.append(call)
        if len(unique) < 2 or len(sources) < 2:
            return []
        return unique

    def reason(state: TurnState) -> dict:
        if memory is not None:
            remembered = memory.respond(state["user_input"])
            if remembered is not None:
                conversation.add(state["user_input"], remembered)
                return _direct(remembered)
        planned = plan_deterministic(state["user_input"])
        if len(planned) > 1:
            return {
                "llm_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "tool_name": "",
                "tool_args": {},
                "tool_calls": planned,
                "response": "",
            }
        if len(planned) == 1:
            return {
                "llm_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "tool_name": planned[0]["name"],
                "tool_args": planned[0]["args"],
                "tool_calls": [],
                "response": "",
            }
        if github is not None:
            action, github_args = github_request(state["user_input"])
            if action:
                return {
                    "llm_seconds": 0.0,
                    "load_seconds": 0.0,
                    "prompt_chars": 0,
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "tokens_per_second": 0.0,
                    "tool_name": action,
                    "tool_args": github_args,
                    "response": "",
                }
        if calendar is not None:
            action, calendar_args = calendar_request(state["user_input"])
            if action:
                return {
                    "llm_seconds": 0.0,
                    "load_seconds": 0.0,
                    "prompt_chars": 0,
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "tokens_per_second": 0.0,
                    "tool_name": action,
                    "tool_args": calendar_args,
                    "response": "",
                }
        if files is not None:
            kind, file_args = filesystem_request(state["user_input"], files.roots())
            if kind == "refused":
                conversation.add(state["user_input"], REFUSED)
                return _direct(REFUSED)
            if kind == "missing":
                conversation.add(state["user_input"], UNSEEN)
                return _direct(UNSEEN)
            if kind:
                return {
                    "llm_seconds": 0.0,
                    "load_seconds": 0.0,
                    "prompt_chars": 0,
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "tokens_per_second": 0.0,
                    "tool_name": kind,
                    "tool_args": file_args,
                    "response": "",
                }
        if model is None:
            text = llm_error or "The local model is unavailable."
            return {
                "response": text,
                "llm_seconds": 0.0,
                "tool_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "tool_name": "",
                "tool_args": {},
            }
        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for role, content in conversation.turns:
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=state["user_input"]))
        query = ""
        if search is not None and not needs_calculator(state["user_input"]):
            query = search_query(state["user_input"])
        if query:
            return {
                "llm_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "tool_name": "web_search",
                "tool_args": {"query": query},
                "response": "",
            }
        page_url = resolve_page(state["user_input"]) if browser is not None else ""
        if page_url:
            return {
                "llm_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "tool_name": "browser_navigate",
                "tool_args": {"url": page_url},
                "response": "",
            }
        asking_for_math = needs_calculator(state["user_input"])
        asking_for_page = needs_browser(state["user_input"]) and browser_model is not None
        if asking_for_math:
            active = tooled
        elif asking_for_page:
            active = browser_model
        else:
            active = model
        started = time.perf_counter()
        message = active.invoke(messages)
        elapsed = time.perf_counter() - started
        size = prompt_chars(messages)
        stats = generation_stats(message, elapsed)
        calls = getattr(message, "tool_calls", None) or []
        if asking_for_math and not calls:
            expression = expression_from_text(message_text(message))
            if expression:
                calls = [
                    {
                        "name": "calculator",
                        "args": {"expression": expression},
                        "id": "text",
                    }
                ]
        if (asking_for_math or asking_for_page) and calls:
            call = calls[0]
            args = call.get("args") if isinstance(call, dict) else {}
            name = call.get("name") if isinstance(call, dict) else ""
            if not isinstance(args, dict):
                args = {}
            return {
                "llm_seconds": elapsed,
                "load_seconds": stats["load_seconds"],
                "prompt_chars": size,
                "prompt_tokens": stats["prompt_tokens"],
                "output_tokens": stats["output_tokens"],
                "tokens_per_second": stats["tokens_per_second"],
                "tool_name": name or "",
                "tool_args": args,
                "tool_calls": [],
                "response": "",
            }
        text = message_text(message) or "I don't have an answer for that."
        conversation.add(state["user_input"], text)
        return {
            "response": text,
            "llm_seconds": elapsed,
            "tool_seconds": 0.0,
            "load_seconds": stats["load_seconds"],
            "prompt_chars": size,
            "prompt_tokens": stats["prompt_tokens"],
            "output_tokens": stats["output_tokens"],
            "tokens_per_second": stats["tokens_per_second"],
            "tool_name": "",
            "tool_args": {},
            "tool_calls": [],
        }

    def run_tool(state: TurnState) -> dict:
        started = time.perf_counter()
        name = state["tool_name"]
        args = state["tool_args"] if isinstance(state["tool_args"], dict) else {}
        if name == "calculator":
            expression = args.get("expression", "")
            if not isinstance(expression, str) or not expression.strip():
                text = "The tool request was not valid."
            else:
                text = calculate(expression)
            if text == "That calculation is not allowed." and model is not None:
                text = _answer_directly(model, conversation, state["user_input"])
        elif name in {
            "get_me",
            "list_my_repos",
            "list_issues",
            "list_pull_requests",
        } and github is not None:
            text = _answer_from_github(github, model, state["user_input"], name, args)
        elif name in {
            "list_events",
            "get_event",
            "list_calendars",
            "search_events",
            "suggest_time",
        } and calendar is not None:
            text = _answer_from_calendar(
                calendar, model, state["user_input"], name, args
            )
        elif name in {"list_directory", "read_text_file", "search_files"} and files is not None:
            text = _answer_from_files(files, model, state["user_input"], name, args)
        elif name == "web_search" and search is not None:
            text = _answer_from_search(search, model, state["user_input"], args)
        elif name in ALLOW and browser is not None:
            text = _read_page(browser, model, state["user_input"], name, args)
        else:
            text = "That tool is not available."
        elapsed = time.perf_counter() - started
        conversation.add(state["user_input"], text)
        return {
            "response": text,
            "tool_seconds": elapsed,
        }

    def run_multi(state: TurnState) -> dict:
        """Run independent tool calls together, then speak one short answer."""
        calls = state.get("tool_calls") or []
        started = time.perf_counter()

        def run_one(call: dict) -> tuple[dict, str]:
            name = call.get("name", "")
            args = call.get("args", {})
            part = call.get("part", "")
            if name in {"calculator", "time", "date"}:
                text = run_tool(
                    {
                        "user_input": part or state["user_input"],
                        "tool_name": name,
                        "tool_args": args,
                    }
                )["response"]
                return call, text
            if name == "web_search" and search is not None:
                return call, search.call(args.get("query", ""))
            if name in {"get_me", "list_my_repos", "list_issues", "list_pull_requests"}:
                if github is None:
                    return call, "GitHub is not available."
                return call, github.call(name, args)
            if name in {
                "list_events",
                "get_event",
                "list_calendars",
                "search_events",
                "suggest_time",
            }:
                if calendar is None:
                    return call, CALENDAR_UNAVAILABLE
                return call, calendar.call(name, args)
            if name in {"read_text_file", "list_directory", "search_files"}:
                if files is None:
                    return call, UNAVAILABLE
                return call, files.call(name, args)
            if name in ALLOW and browser is not None:
                page_url = args.get("url", "")
                opened = browser.call("browser_navigate", {"url": page_url})
                if opened == "Playwright is not available.":
                    return call, opened
                page = browser.call("browser_snapshot", {})
                return call, trim_page(page)
            return call, "That tool is not available."

        results: dict[tuple[str, str], str] = {}
        with ThreadPoolExecutor(max_workers=min(len(calls), 4)) as pool:
            for call, text in pool.map(run_one, calls):
                key = (
                    call.get("name", ""),
                    json.dumps(call.get("args", {}), sort_keys=True),
                )
                results[key] = text
        elapsed = time.perf_counter() - started

        lines = []
        for call in calls:
            key = (
                call.get("name", ""),
                json.dumps(call.get("args", {}), sort_keys=True),
            )
            found = (results.get(key) or "").strip()
            trimmed = " ".join(found.split())
            if len(trimmed) > 600:
                trimmed = trimmed[:600]
            lines.append(f"- {call.get('part', call['name'])}: {trimmed or 'no result'}")
        if tooled is None:
            text = " ".join(line[2:] for line in lines)[:600] or "I have no answer."
        else:
            started_answer = time.perf_counter()
            messages = [
                SystemMessage(
                    content=(
                        "Answer in one or two short sentences "
                        "using only these tool results."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Question: {state['user_input']}\n\nResults:\n"
                        + "\n".join(lines)
                    )
                ),
            ]
            text = message_text(tooled.invoke(messages)) or "I have no answer."
            llm_answer_seconds = time.perf_counter() - started_answer
        conversation.add(state["user_input"], text)
        update: dict = {
            "response": text,
            "tool_seconds": elapsed,
            "tool_name": "",
            "tool_args": {},
            "tool_calls": [],
        }
        if tooled is not None:
            update["llm_seconds"] = llm_answer_seconds
            update["prompt_chars"] = sum(len(line) for line in lines)
            update["tokens_per_second"] = 0.0
        return update

    def choose_path(state: TurnState) -> str:
        if state["route"] == "fast":
            return "fast"
        return "reason"

    def after_reason(state: TurnState) -> str:
        if state.get("tool_calls"):
            return "run_multi"
        if state.get("tool_name"):
            return "run_tool"
        return END

    graph = StateGraph(TurnState)
    graph.add_node("route", route)
    graph.add_node("fast", fast)
    graph.add_node("reason", reason)
    graph.add_node("run_tool", run_tool)
    graph.add_node("run_multi", run_multi)
    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        choose_path,
        {"fast": "fast", "reason": "reason"},
    )
    graph.add_edge("fast", END)
    graph.add_conditional_edges(
        "reason",
        after_reason,
        {"run_multi": "run_multi", "run_tool": "run_tool", END: END},
    )
    graph.add_edge("run_tool", END)
    graph.add_edge("run_multi", END)
    return graph.compile()


def _direct(text: str) -> dict:
    return {
        "response": text,
        "llm_seconds": 0.0,
        "tool_seconds": 0.0,
        "load_seconds": 0.0,
        "prompt_chars": 0,
        "prompt_tokens": 0,
        "output_tokens": 0,
        "tokens_per_second": 0.0,
        "tool_name": "",
        "tool_args": {},
        "tool_calls": [],
    }


def _answer_from_github(github, model, user_input: str, name: str, args: dict) -> str:
    found = github.call(name, args)
    if name == "list_my_repos" and found not in {
        "GitHub needs an access token in .env.",
        "GitHub is not available.",
        "GitHub refused the access token.",
        "That GitHub action is not available.",
    }:
        from app.mcp.github import repo_names_from_tool_text

        total, names = repo_names_from_tool_text(found)
        if names:
            listed = ", ".join(names)
            extra = f" And {total - len(names)} more." if total > len(names) else ""
            return f"You have {total} public repos: {listed}.{extra}"
        return found or "GitHub is not available."
    trimmed = " ".join(found.split())
    if len(trimmed) > 1200:
        trimmed = trimmed[:1200]
    if model is None or found in {
        "GitHub needs an access token in .env.",
        "GitHub is not available.",
        "GitHub refused the access token.",
        "That GitHub action is not available.",
    }:
        return trimmed
    messages = [
        SystemMessage(
            content=(
                "Answer in one or two short sentences using only this GitHub text."
            )
        ),
        HumanMessage(content=f"Question: {user_input}\n\nGitHub:\n{trimmed}"),
    ]
    message = model.invoke(messages)
    return message_text(message) or "GitHub is not available."


def _answer_from_calendar(calendar, model, user_input: str, name: str, args: dict) -> str:
    found = calendar.call(name, args)
    if found in {CALENDAR_MISSING, CALENDAR_UNAVAILABLE}:
        return found
    if name in {"list_events", "search_events"}:
        lines = events_from_tool_text(found)
        if lines:
            joined = "; ".join(lines)
            if model is None:
                return joined
            messages = [
                SystemMessage(
                    content=(
                        "Answer in one or two short sentences using only these events."
                    )
                ),
                HumanMessage(content=f"Question: {user_input}\n\nEvents:\n{joined}"),
            ]
            message = model.invoke(messages)
            return message_text(message) or joined
        return "You have nothing scheduled there."
    trimmed = " ".join(found.split())
    if len(trimmed) > 1200:
        trimmed = trimmed[:1200]
    if model is None:
        return trimmed or CALENDAR_UNAVAILABLE
    messages = [
        SystemMessage(
            content=(
                "Answer in one or two short sentences using only this calendar text."
            )
        ),
        HumanMessage(content=f"Question: {user_input}\n\nCalendar:\n{trimmed}"),
    ]
    message = model.invoke(messages)
    return message_text(message) or CALENDAR_UNAVAILABLE



def _answer_from_files(files, model, user_input: str, name: str, args: dict) -> str:
    found = files.call(name, args)
    if found in {REFUSED, UNSEEN, UNAVAILABLE}:
        return found
    trimmed = " ".join(found.split())
    if len(trimmed) > 1200:
        trimmed = trimmed[:1200]
    if model is None:
        return trimmed or UNSEEN
    messages = [
        SystemMessage(
            content=(
                "Answer in one or two short sentences using only this file text."
            )
        ),
        HumanMessage(content=f"Question: {user_input}\n\nFiles:\n{trimmed}"),
    ]
    message = model.invoke(messages)
    return message_text(message) or UNSEEN


def _answer_from_search(search, model, user_input: str, args: dict) -> str:
    query = args.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return "I need something to search for."
    found = search.call(query)
    if found == "Web search is not available.":
        return found
    if model is None:
        return found or "I could not find web results for that."
    messages = [
        SystemMessage(
            content=(
                "Answer in one or two short sentences using only the search results."
            )
        ),
        HumanMessage(content=f"Question: {user_input}\n\nResults:\n{found}"),
    ]
    message = model.invoke(messages)
    return message_text(message) or "I could not find web results for that."


def _read_page(browser, model, user_input: str, name: str, args: dict) -> str:
    if name != "browser_navigate":
        return "That tool is not available."
    url = args.get("url", "")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return "I can only open an http or https page."
    opened = browser.call("browser_navigate", {"url": url})
    if opened == "Playwright is not available.":
        return opened
    page = trim_page(browser.call("browser_snapshot", {}))
    if page == "Playwright is not available.":
        return page
    if model is None:
        return page or "I could not read that page."
    messages = [
        SystemMessage(
            content=(
                "Answer in one or two short sentences using only the page text."
            )
        ),
        HumanMessage(content=f"Question: {user_input}\n\nPage:\n{page}"),
    ]
    message = model.invoke(messages)
    return message_text(message) or "I could not read that page."


def _answer_directly(model, conversation: Conversation, user_input: str) -> str:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for role, content in conversation.turns:
        if content == "That calculation is not allowed.":
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_input))
    message = model.invoke(messages)
    return message_text(message) or "I don't have an answer for that."
