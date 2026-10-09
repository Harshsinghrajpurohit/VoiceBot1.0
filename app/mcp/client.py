"""Small MCP client over stdio. No extra package."""

import json
import os
import shutil
import subprocess
import threading
from queue import Empty, Queue


class McpError(Exception):
    """The MCP server did not complete a call."""


def encode(message: dict) -> bytes:
    """One JSON object per line. That is the framing Playwright MCP reads."""
    return (json.dumps(message) + "\n").encode("utf-8")


class StdioClient:
    def __init__(self, command: list[str]):
        self.command = command
        self.process = None
        self.queue = Queue()
        self.stderr_lines = []
        self.next_id = 1

    def start(self) -> None:
        self.process = subprocess.Popen(
            _windows_command(self.command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "voicebot", "version": "0.1"},
            },
            timeout=180,
        )
        self._notify("notifications/initialized")

    def _drain_stderr(self) -> None:
        stderr = self.process.stderr if self.process is not None else None
        if stderr is None:
            return
        for line in stderr:
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self.stderr_lines.append(text)
                self.stderr_lines = self.stderr_lines[-20:]

    def _read(self) -> None:
        stdout = self.process.stdout
        try:
            while True:
                line = stdout.readline()
                if line == b"":
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text.startswith("{"):
                    continue
                self.queue.put(json.loads(text))
        except Exception as exc:
            detail = " ".join(self.stderr_lines[-3:])
            text = str(exc)
            if detail:
                text = text + " " + detail
            self.queue.put({"error": text})

    def _send(self, message: dict) -> None:
        if self.process is None or self.process.stdin is None:
            raise McpError("The MCP server is not running.")
        self.process.stdin.write(encode(message))
        self.process.stdin.flush()

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict, timeout: float = 60) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        while True:
            try:
                message = self.queue.get(timeout=timeout)
            except Empty as exc:
                detail = " ".join(self.stderr_lines[-3:])
                message = "Playwright did not answer in time."
                if detail:
                    message = message + " " + detail
                raise McpError(message) from exc
            if message.get("error") and "id" not in message:
                detail = message.get("error") or "The MCP server closed."
                raise McpError(str(detail))
            if message.get("id") != request_id:
                continue
            if "error" in message and message["error"]:
                raise McpError("The MCP call failed.")
            return message.get("result") or {}

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout=180,
        )
        if result.get("isError"):
            detail = _result_text(result) or "The MCP call failed."
            raise McpError(detail)
        return _result_text(result)

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None:
            self.process.stdin.close()
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.process = None


def _result_text(result: dict) -> str:
    parts = []
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "\n".join(parts).strip()


def _windows_command(command: list[str]) -> list[str]:
    """Start an npx server with node.exe. Windows cannot pipe to npx.cmd."""
    if not command:
        return command
    resolved = shutil.which(command[0]) or command[0]
    node = shutil.which("node")
    if os.name != "nt" or not node or not os.path.basename(resolved).lower().startswith("npx"):
        return [resolved, *command[1:]]
    package, server_args = _split_npx_args(command[1:])
    entry = _find_package_entry(package) if package else None
    if entry is None and package:
        _install_npx_package(node, package)
        entry = _find_package_entry(package)
    if entry:
        return [node, entry, *server_args]
    return [resolved, *command[1:]]


def _split_npx_args(args: list[str]) -> tuple[str | None, list[str]]:
    package = None
    server_args = []
    for arg in args:
        if arg in ("-y", "--yes"):
            continue
        if package is None and not arg.startswith("-"):
            package = arg
            continue
        server_args.append(arg)
    return package, server_args


def _install_npx_package(node: str, package: str) -> None:
    script = os.path.join(
        os.path.dirname(node),
        "node_modules",
        "npm",
        "bin",
        "npx-cli.js",
    )
    if not os.path.isfile(script):
        return
    subprocess.run(
        [node, script, "-y", "--package", package, "node", "-e", "process.exit(0)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=False,
    )


def _find_package_entry(package: str) -> str | None:
    scope, name = _package_parts(package)
    if not name:
        return None
    for root in _npx_cache_roots():
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            if os.path.basename(dirpath) != name or "package.json" not in filenames:
                continue
            parent = os.path.basename(os.path.dirname(dirpath))
            if scope and parent != scope:
                continue
            if not scope and parent != "node_modules":
                continue
            entry = _bin_entry(os.path.join(dirpath, "package.json"))
            if entry:
                return entry
    return None


def _package_parts(package: str) -> tuple[str, str]:
    spec = package.strip()
    if spec.startswith("@"):
        body = spec[1:]
        scope, _, rest = body.partition("/")
        return "@" + scope, rest.split("@", 1)[0]
    return "", spec.split("@", 1)[0]


def _npx_cache_roots() -> list[str]:
    roots = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "npm-cache", "_npx"))
    cache = os.environ.get("NPM_CONFIG_CACHE")
    if cache:
        roots.append(os.path.join(cache, "_npx"))
    return roots


def _bin_entry(package_json: str) -> str | None:
    try:
        with open(package_json, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    bin_field = data.get("bin")
    relative = ""
    if isinstance(bin_field, str):
        relative = bin_field
    elif isinstance(bin_field, dict) and bin_field:
        relative = next(iter(bin_field.values()))
    base = os.path.dirname(package_json)
    if relative:
        candidate = os.path.normpath(os.path.join(base, relative))
        if os.path.isfile(candidate):
            return candidate
    for candidate in (
        os.path.join(base, "dist", "index.js"),
        os.path.join(base, "cli.js"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None
