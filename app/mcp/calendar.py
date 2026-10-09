"""Google Calendar remote MCP. Read-only plus free-busy. No local server."""

import json
import re
from datetime import date, datetime, time, timedelta


REMOTE_URL = "https://calendarmcp.googleapis.com/mcp/v1"
ALLOW = frozenset(
    {"list_events", "get_event", "list_calendars", "search_events", "suggest_time"}
)
MISSING = "Calendar needs a Google sign-in first."
UNAVAILABLE = "Calendar is not available."
NOT_ALLOWED = "That calendar action is not available."
MAX_LISTED = 5

_TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_THIS_WEEK = re.compile(r"\bthis week\b", re.IGNORECASE)
_CALENDARS = re.compile(
    r"\b(list (?:my )?calendars|my calendars|which calendars)\b", re.IGNORECASE
)
_SEARCH = re.compile(
    r"\b(?:search (?:my )?calendar for|find (?:on|in)(?: my)? calendar|"
    r"when is(?: my)?)\s+(.+)$",
    re.IGNORECASE,
)
_ON_CALENDAR = re.compile(
    r"\b(what(?:'s| is)(?: on)?(?: my)? calendar|what do i have|"
    r"what(?:'s| is) (?:on|next)|my schedule|my agenda|my events)\b",
    re.IGNORECASE,
)
_FREE = re.compile(
    r"\b(am i free|when am i free|find (?:me )?(?:a )?free time|"
    r"suggest (?:a )?time|free busy|freebusy)\b",
    re.IGNORECASE,
)


def day_range(day: date) -> tuple[str, str]:
    """Local-time ISO bounds for one day. No UTC offset, per the schema."""
    start = datetime.combine(day, time.min).strftime("%Y-%m-%dT%H:%M:%S")
    end = datetime.combine(day + timedelta(days=1), time.min).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    return start, end


def week_range(today: date) -> tuple[str, str]:
    """Monday to next Monday in local-time ISO."""
    monday = today - timedelta(days=today.weekday())
    start = datetime.combine(monday, time.min).strftime("%Y-%m-%dT%H:%M:%S")
    end = datetime.combine(monday + timedelta(days=7), time.min).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    return start, end


def calendar_request(text: str, today: date | None = None) -> tuple[str, dict]:
    """Map a spoken calendar question to one allowed tool call."""
    cleaned = text.strip().rstrip("?.!")
    if _CALENDARS.search(cleaned):
        return "list_calendars", {}
    if _FREE.search(cleaned):
        return "suggest_time", {}
    searching = _SEARCH.search(cleaned)
    if searching:
        return "search_events", {"query": searching.group(1).strip().rstrip("?.!")}
    if not _ON_CALENDAR.search(cleaned):
        return "", {}
    day = today or date.today()
    if _TOMORROW.search(cleaned):
        start, end = day_range(day + timedelta(days=1))
    elif _THIS_WEEK.search(cleaned):
        start, end = week_range(day)
    else:
        start, end = day_range(day)
    return "list_events", {"startTime": start, "endTime": end, "pageSize": 10}


def events_from_tool_text(text: str, limit: int = MAX_LISTED) -> list[str]:
    """Short 'title at time' lines from a list/search payload."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("summary") or item.get("title") or "Untitled"
        moment = ""
        start = item.get("start") or {}
        if isinstance(start, dict):
            moment = start.get("dateTime") or start.get("date") or ""
        lines.append(f"{title} at {moment}" if moment else str(title))
        if len(lines) >= limit:
            break
    return lines


class Calendar:
    """Client for the official remote Calendar MCP. Read-only plus free-busy."""

    def __init__(self, settings, token_path: str = ""):
        from app.mcp import google_auth

        self.url = settings.calendar_mcp_url or REMOTE_URL
        self.client_json = (settings.google_client_json or "").strip()
        self.token_path = token_path or "data/google_token.json"
        self.client = None
        self._auth = google_auth

    def call(self, action: str, arguments: dict) -> str:
        from app.mcp.client import McpError
        from app.mcp.http_client import HttpClient

        if action not in ALLOW:
            return NOT_ALLOWED
        if not self.client_json:
            return MISSING
        token = self._auth.load_refresh_token(self.token_path)
        if not token:
            return MISSING
        access = self._auth.refresh_access_token(self.client_json, token)
        if not access:
            return MISSING
        try:
            if self.client is None:
                client = HttpClient(self.url, {"Authorization": "Bearer " + access})
                client.start()
                self.client = client
            return self.client.call_tool(action, arguments)
        except (McpError, OSError, TimeoutError) as exc:
            print(f"Calendar: {exc}")
            self.close()
            if str(exc) == "The access token was refused.":
                return MISSING
            return UNAVAILABLE

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
