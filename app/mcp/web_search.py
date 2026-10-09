"""Web search MCP client. Starts only when a question needs current information."""

import re
import sys

from app.mcp.client import McpError, StdioClient


_EXPLICIT = re.compile(
    r"^(?:please\s+)?(?:search(?:\s+google)?\s+for|look\s+up|google)\s+(.+)$",
    re.IGNORECASE,
)
_CURRENT = re.compile(
    r"\b(weather|forecast|news|headline|score|stock price|price of|"
    r"latest|today|tonight|this week|right now|who won)\b",
    re.IGNORECASE,
)


def search_query(text: str) -> str:
    """Return the search text when this question needs the web. Empty otherwise."""
    cleaned = text.strip().rstrip("?.!")
    explicit = _EXPLICIT.match(cleaned)
    if explicit:
        return explicit.group(1).strip().rstrip("?.!")
    if _CURRENT.search(cleaned):
        return cleaned
    return ""


class WebSearch:
    """One local search server. No API key."""

    def __init__(self):
        self.client = None

    def command(self) -> list[str]:
        return [sys.executable, "-m", "app.mcp.search_server"]

    def call(self, query: str) -> str:
        if not query.strip():
            return "I need something to search for."
        client = self.client
        try:
            if client is None:
                client = StdioClient(self.command())
                client.start()
                self.client = client
            return client.call_tool("web_search", {"query": query})
        except (McpError, OSError, TimeoutError) as exc:
            print(f"Web search: {exc}")
            if self.client is not None:
                self.client.close()
            self.client = None
            return "Web search is not available."

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
