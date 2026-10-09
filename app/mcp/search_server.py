"""Local web search MCP. No API key. Speaks one JSON message per line."""

import json
import re
import sys
import urllib.parse
import urllib.request
from html import unescape


_LINK = re.compile(r"class='result-link'>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_SNIPPET = re.compile(r"class='result-snippet'>(.*?)</td>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def clean(text: str) -> str:
    plain = _TAG.sub(" ", unescape(text))
    return " ".join(plain.split())


def format_results(page: str, limit: int = 4) -> str:
    titles = [clean(item) for item in _LINK.findall(page)]
    snippets = [clean(item) for item in _SNIPPET.findall(page)]
    lines = []
    for index, title in enumerate(titles):
        if not title:
            continue
        snippet = snippets[index] if index < len(snippets) else ""
        line = title if not snippet else f"{title}. {snippet}"
        lines.append(line)
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def fetch_results(query: str) -> str:
    cleaned = query.strip()
    if not cleaned:
        return ""
    target = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode(
        {"q": cleaned}
    )
    request = urllib.request.Request(target, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        page = response.read().decode("utf-8", errors="replace")
    return format_results(page)


def encode(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def read_message():
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    text = line.decode("utf-8", errors="replace").strip()
    if not text.startswith("{"):
        return None
    return json.loads(text)


def search_text(arguments: dict) -> tuple[str, bool]:
    query = arguments.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return "I need something to search for.", True
    try:
        text = fetch_results(query)
    except (OSError, TimeoutError):
        return "Web search is not available.", True
    if not text:
        return "I could not find web results for that.", True
    return text, False


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            return
        if "id" not in message:
            continue
        method = message.get("method")
        request_id = message.get("id")
        failed = False
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {}}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "web_search",
                        "description": "Search the web for current information.",
                    }
                ]
            }
        elif method == "tools/call":
            params = message.get("params") or {}
            if params.get("name") != "web_search":
                result = {
                    "content": [{"type": "text", "text": "That tool is not available."}],
                    "isError": True,
                }
            else:
                text, failed = search_text(params.get("arguments") or {})
                result = {
                    "content": [{"type": "text", "text": text}],
                    "isError": failed,
                }
        else:
            result = {}
        sys.stdout.buffer.write(
            encode({"jsonrpc": "2.0", "id": request_id, "result": result})
        )
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
