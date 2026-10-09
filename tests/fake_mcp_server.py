"""Fake MCP server for tests. Speaks the stdio framing."""

import json
import sys


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


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            return
        if "id" not in message:
            continue
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {}}
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": "browser_navigate"},
                    {"name": "browser_snapshot"},
                    {"name": "browser_evaluate"},
                ]
            }
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            url = (params.get("arguments") or {}).get("url", "")
            if name == "browser_navigate":
                text = f"Opened {url}"
            else:
                text = "heading Example Domain"
            result = {"content": [{"type": "text", "text": text}]}
        else:
            result = {}
        sys.stdout.buffer.write(
            encode({"jsonrpc": "2.0", "id": request_id, "result": result})
        )
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
