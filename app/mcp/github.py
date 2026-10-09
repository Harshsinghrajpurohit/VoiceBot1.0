"""GitHub's remote MCP server. Read-only. No local server and no Docker."""

import json
import re

from app.mcp.client import McpError
from app.mcp.http_client import HttpClient


REMOTE_URL = "https://api.githubcopilot.com/mcp/"
TOOLSETS = "repos,issues,pull_requests,users"
MISSING = "GitHub needs an access token in .env."
UNAVAILABLE = "GitHub is not available."
NOT_ALLOWED = "That GitHub action is not available."
MAX_LISTED = 10

_MUTATION = re.compile(
    r"(write|create|update|delete|merge|push|comment|close_|add_|request_copilot)",
    re.IGNORECASE,
)
_ME = re.compile(
    r"\b(who am i on github|my github account|my github user|my github profile)\b",
    re.IGNORECASE,
)
_REPOS = re.compile(
    r"\b(my github repos|my github repositories|list my github repos|"
    r"list my repositories|list my repos)\b",
    re.IGNORECASE,
)
_ISSUES = re.compile(
    r"\bgithub issues (?:in|for|on) ([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
_PULLS = re.compile(
    r"\bpull requests (?:in|for|on) ([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
_LOGIN = re.compile(r'"login"\s*:\s*"([^"]+)"')


def github_headers(token: str) -> dict[str, str]:
    headers = {
        "X-MCP-Toolsets": TOOLSETS,
        "X-MCP-Readonly": "true",
        "X-MCP-Tools": "get_me",
    }
    if token.strip():
        headers["Authorization"] = "Bearer " + token.strip()
    return headers


def github_request(text: str) -> tuple[str, dict]:
    """Map a spoken GitHub question to one read-only action."""
    cleaned = text.strip().rstrip("?.!")
    if _ME.search(cleaned):
        return "get_me", {}
    if _REPOS.search(cleaned):
        return "list_my_repos", {}
    issues = _ISSUES.search(cleaned)
    if issues:
        return "list_issues", {"owner": issues.group(1), "repo": issues.group(2)}
    pulls = _PULLS.search(cleaned)
    if pulls:
        return "list_pull_requests", {
            "owner": pulls.group(1),
            "repo": pulls.group(2),
        }
    return "", {}


class GitHub:
    """Client for https://api.githubcopilot.com/mcp/."""

    def __init__(self, settings):
        self.token = settings.github_token.strip()
        self.url = settings.github_mcp_url or REMOTE_URL
        self.client = None
        self.tool_names: set[str] = set()

    def call(self, action: str, arguments: dict) -> str:
        if action not in {"get_me", "list_my_repos", "list_issues", "list_pull_requests"}:
            return NOT_ALLOWED
        if not self.token:
            return MISSING
        try:
            self._ensure()
            if action == "get_me":
                return self._tool("get_me", {})
            if action == "list_my_repos":
                return self._my_repos()
            if action == "list_issues":
                return self._read_list("issue_read", "list_issues", arguments)
            return self._read_list("pull_request_read", "list_pull_requests", arguments)
        except (McpError, OSError, TimeoutError) as exc:
            print(f"GitHub: {exc}")
            self.close()
            if str(exc) == "The access token was refused.":
                return "GitHub refused the access token."
            return UNAVAILABLE

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.tool_names = set()

    def _ensure(self) -> None:
        if self.client is not None:
            return
        client = HttpClient(self.url, github_headers(self.token))
        client.start()
        self.client = client
        self.tool_names = {
            tool.get("name", "")
            for tool in client.list_tools()
            if isinstance(tool, dict)
        }

    def _my_repos(self) -> str:
        me = self._tool("get_me", {})
        login = login_from_tool_text(me)
        if not login:
            return me or UNAVAILABLE
        return self._tool(
            "search_repositories",
            {"query": f"user:{login}", "perPage": 5},
        )

    def _read_list(self, read_tool: str, list_tool: str, arguments: dict) -> str:
        owner = arguments.get("owner", "")
        repo = arguments.get("repo", "")
        if read_tool in self.tool_names:
            return self._tool(
                read_tool,
                {
                    "method": "list",
                    "owner": owner,
                    "repo": repo,
                    "state": "open",
                    "perPage": 5,
                },
            )
        return self._tool(
            list_tool,
            {"owner": owner, "repo": repo, "state": "open", "perPage": 5},
        )

    def _tool(self, name: str, arguments: dict) -> str:
        if _MUTATION.search(name) or name not in self.tool_names:
            return NOT_ALLOWED
        if self.client is None:
            return UNAVAILABLE
        return self.client.call_tool(name, arguments)


def login_from_tool_text(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("login"), str):
        return data["login"]
    found = _LOGIN.search(text)
    return found.group(1) if found else ""


def repo_names_from_tool_text(text: str, limit: int = MAX_LISTED) -> tuple[int, list[str]]:
    """Names from a search_repositories payload. Total first, then up to limit."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return 0, []
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return 0, []
    total = data.get("total_count")
    names = []
    for item in data["items"]:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        if len(names) >= limit:
            break
    total = total if isinstance(total, int) else len(names)
    return total, names
