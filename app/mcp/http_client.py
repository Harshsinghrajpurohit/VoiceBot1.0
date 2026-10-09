"""MCP client for a remote Streamable HTTP server. No extra package."""

import json
import urllib.error
import urllib.request

from app.mcp.client import McpError, _result_text


def parse_http_body(raw: str, content_type: str) -> list[dict]:
    text = raw.strip()
    if not text:
        return []
    if "text/event-stream" in content_type.lower() or text.startswith("data:"):
        messages = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            messages.append(json.loads(payload))
        return messages
    message = json.loads(text)
    return [message] if isinstance(message, dict) else []


class HttpClient:
    """Talks to one remote MCP endpoint. The caller supplies headers."""

    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.headers = dict(headers)
        self.session_id = ""
        self.next_id = 1

    def start(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "voicebot", "version": "0.1"},
            },
        )
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        if result.get("isError"):
            detail = _result_text(result) or "The MCP call failed."
            raise McpError(detail)
        return _result_text(result)

    def close(self) -> None:
        if not self.session_id:
            return
        request = urllib.request.Request(self.url, method="DELETE", headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=3):
                pass
        except (OSError, urllib.error.URLError):
            pass
        self.session_id = ""

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        }
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _notify(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        messages = self._post(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        for message in messages:
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise McpError("The MCP call failed.")
            return message.get("result") or {}
        raise McpError("The remote MCP server did not answer.")

    def _post(self, message: dict) -> list[dict]:
        body = json.dumps(message).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                self._remember_session(response.headers)
                raw = response.read().decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            self._remember_session(exc.headers)
            if exc.code == 202:
                return []
            if exc.code in {401, 403}:
                raise McpError("The access token was refused.") from exc
            raise McpError("The remote MCP server did not answer.") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise McpError("The remote MCP server did not answer.") from exc
        try:
            return parse_http_body(raw, content_type)
        except json.JSONDecodeError as exc:
            raise McpError("The remote MCP server did not answer.") from exc

    def _remember_session(self, headers) -> None:
        if headers is None:
            return
        session = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
        if session:
            self.session_id = session
