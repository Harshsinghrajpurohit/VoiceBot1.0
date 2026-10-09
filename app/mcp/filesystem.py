"""Filesystem MCP. Read-only, and only inside the allowed folders."""

import os
import re

from app.mcp.client import McpError, StdioClient


READ_TOOLS = frozenset(
    {
        "read_text_file",
        "list_directory",
        "search_files",
        "get_file_info",
        "list_allowed_directories",
    }
)
REFUSED = "I can look at files, but I will not change or delete them."
UNSEEN = "I cannot see that file."
UNAVAILABLE = "Filesystem is not available."
READ_LINES = 40

_ALIASES = {
    "documents": "Documents",
    "document": "Documents",
    "my documents": "Documents",
    "downloads": "Downloads",
    "download": "Downloads",
    "desktop": "Desktop",
    "my desktop": "Desktop",
}
_CHANGE = re.compile(
    r"\b(delete|remove|erase|move|rename|write|edit|overwrite|create)\b",
    re.IGNORECASE,
)
_FILE_WORD = re.compile(
    r"\b(file|files|folder|folders|directory|desktop|documents|downloads)\b",
    re.IGNORECASE,
)
_LIST = re.compile(
    r"^(?:please\s+)?(?:"
    r"list(?: my| the)? files|"
    r"show(?: me)?(?: my| the)? files|"
    r"what files are (?:in|on)"
    r")\s*(?:in|on|from)?\s*(.*)$",
    re.IGNORECASE,
)
_READ = re.compile(
    r"^(?:please\s+)?read(?: the)? file\s+(.+)$",
    re.IGNORECASE,
)
_FIND = re.compile(
    r"^(?:please\s+)?(?:find|search for)(?: the)? file\s+(.+)$",
    re.IGNORECASE,
)


def default_roots() -> list[str]:
    home = os.path.expanduser("~")
    roots = []
    for name in ("Documents", "Downloads", "Desktop"):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            roots.append(path)
    return roots


def parse_roots(value: str) -> list[str]:
    if not value.strip():
        return default_roots()
    roots = []
    for part in value.split(os.pathsep):
        path = os.path.expanduser(part.strip().strip("\"'"))
        if path and os.path.isdir(path):
            roots.append(os.path.realpath(path))
    return roots


def _named_root(spoken: str, roots: list[str]) -> str:
    folder = _ALIASES.get(" ".join(spoken.lower().split()), "")
    if not folder:
        return ""
    for root in roots:
        if os.path.basename(root).lower() == folder.lower():
            return os.path.realpath(root)
    return ""


def inside_roots(path: str, roots: list[str]) -> str:
    try:
        real = os.path.realpath(path)
    except OSError:
        return ""
    for root in roots:
        try:
            base = os.path.realpath(root)
            if os.path.commonpath([real, base]) == base:
                return real
        except ValueError:
            continue
    return ""


def resolve_path(spoken: str, roots: list[str]) -> str:
    text = spoken.strip().strip("\"'")
    if not text or not roots:
        return ""
    pieces = text.replace("/", os.sep).split(os.sep)
    named = _named_root(pieces[0], roots)
    if named:
        candidate = os.path.join(named, *pieces[1:]) if len(pieces) > 1 else named
        return inside_roots(candidate, roots)
    if os.path.isabs(text):
        return inside_roots(text, roots)
    for root in roots:
        candidate = os.path.join(root, text)
        if os.path.exists(candidate):
            return inside_roots(candidate, roots)
    return inside_roots(os.path.join(roots[0], text), roots)


def filesystem_request(text: str, roots: list[str]) -> tuple[str, dict]:
    """Map a spoken file request to one read-only tool call."""
    cleaned = text.strip().rstrip("?.!")
    if _CHANGE.search(cleaned) and _FILE_WORD.search(cleaned):
        return "refused", {}
    listing = _LIST.match(cleaned)
    if listing:
        folder = listing.group(1).strip()
        path = roots[0] if not folder else resolve_path(folder, roots)
        if not path or not os.path.isdir(path):
            return "missing", {}
        return "list_directory", {"path": path}
    reading = _READ.match(cleaned)
    if reading:
        path = resolve_path(reading.group(1), roots)
        if not path or not os.path.isfile(path):
            return "missing", {}
        return "read_text_file", {"path": path, "head": READ_LINES}
    finding = _FIND.match(cleaned)
    if finding:
        name = finding.group(1).strip().strip("\"'")
        if not name or not roots:
            return "missing", {}
        pattern = name if any(mark in name for mark in "*?") else f"*{name}*"
        return "search_files", {
            "path": os.path.realpath(roots[0]),
            "pattern": pattern,
            "excludePatterns": ["**/node_modules/**", "**/.git/**"],
        }
    return "", {}


class Filesystem:
    """Official filesystem MCP, limited to the configured folders."""

    def __init__(self, settings):
        self.settings = settings
        self.client = None
        self._roots = parse_roots(settings.filesystem_roots)

    def roots(self) -> list[str]:
        return list(self._roots)

    def command(self) -> list[str]:
        return [
            "npx",
            "-y",
            "@modelcontextprotocol/server-filesystem",
            *self._roots,
        ]

    def call(self, name: str, arguments: dict) -> str:
        if name not in READ_TOOLS:
            return REFUSED
        if not self._roots:
            return UNAVAILABLE
        client = self.client
        try:
            if client is None:
                client = StdioClient(self.command())
                client.start()
                self.client = client
            return client.call_tool(name, arguments)
        except (McpError, OSError, TimeoutError) as exc:
            print(f"Filesystem: {exc}")
            if self.client is not None:
                self.client.close()
            self.client = None
            return UNAVAILABLE

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
