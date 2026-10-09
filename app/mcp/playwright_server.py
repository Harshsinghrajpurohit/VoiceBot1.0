"""Playwright MCP. Only opening a page and reading it are allowed."""

import re
import shlex
from urllib.parse import quote_plus

from app.mcp.client import McpError, StdioClient

ALLOW = frozenset({"browser_navigate", "browser_snapshot"})
PAGE_LIMIT = 1200

# Spoken names. No model call is used to turn these into addresses.
SITES = {
    "google": "https://www.google.com",
    "chrome": "https://www.google.com",
    "google chrome": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "linkedin": "https://www.linkedin.com",
    "weather": "https://www.google.com/search?q=weather",
}

_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_OPEN = re.compile(
    r"^(?:please\s+)?(?:open|launch|go to|visit)\s+(.+)$",
    re.IGNORECASE,
)
_SEARCH = re.compile(
    r"^(?:please\s+)?(?:search google for|google search for|search for)\s+(.+)$",
    re.IGNORECASE,
)
_FILLER = {"the", "a", "an", "website", "site", "page", "browser", "app", "web"}


def _search_url(query: str) -> str:
    cleaned = query.strip().rstrip("?.!")
    if not cleaned:
        return ""
    return "https://www.google.com/search?q=" + quote_plus(cleaned)


def _target_name(text: str) -> str:
    words = [word for word in text.lower().split() if word not in _FILLER]
    return " ".join(words).strip()


def resolve_page(text: str) -> str:
    """Map a spoken browser request to one http(s) address. Empty if it is not one."""
    cleaned = text.strip().rstrip("?.!")
    found = _URL.search(cleaned)
    if found:
        return found.group(0).rstrip(".,)")
    search = _SEARCH.match(cleaned)
    if search:
        return _search_url(search.group(1))
    opened = _OPEN.match(cleaned)
    if not opened:
        return ""
    target = _target_name(opened.group(1))
    if not target:
        return ""
    if target in SITES:
        return SITES[target]
    return _search_url(target)


def needs_browser(text: str) -> bool:
    return bool(resolve_page(text))


def browser_failure(detail: str) -> str:
    if "Playwright Extension" in detail or "Extension not found" in detail:
        return (
            "Install the Playwright extension in Chrome. "
            "Then I can use the browser you are already signed in to."
        )
    return "Playwright is not available."


def trim_page(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= PAGE_LIMIT:
        return cleaned
    return cleaned[:PAGE_LIMIT]


class PlaywrightBrowser:
    """Starts the official server on the first page request."""

    def __init__(self, settings):
        self.settings = settings
        self.client = None

    def command(self) -> list[str]:
        args = shlex.split(self.settings.playwright_mcp_args, posix=False)
        return [self.settings.playwright_mcp_command, *args]

    def call(self, name: str, arguments: dict) -> str:
        if name not in ALLOW:
            return "That tool is not available."
        client = self.client
        try:
            if client is None:
                client = StdioClient(self.command())
                client.start()
                self.client = client
            return client.call_tool(name, arguments)
        except (McpError, OSError, TimeoutError) as exc:
            print(f"Playwright: {exc}")
            if self.client is not None:
                self.client.close()
            self.client = None
            return browser_failure(str(exc))

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
