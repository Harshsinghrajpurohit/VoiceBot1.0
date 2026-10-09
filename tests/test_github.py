import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.mcp.github import (
    MISSING,
    NOT_ALLOWED,
    GitHub,
    github_headers,
    github_request,
    repo_names_from_tool_text,
)
from app.mcp.http_client import parse_http_body
from tests.test_phase2 import FakeLLM, FakeMessage


class SummaryModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return FakeMessage("You are octocat on GitHub.")


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def call(self, action, arguments):
        self.calls.append((action, arguments))
        return '{"login":"octocat"}'


def _settings(url: str, token: str = "test-token"):
    return type(
        "Settings",
        (),
        {"github_token": token, "github_mcp_url": url},
    )()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        message = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.seen_headers.append(dict(self.headers))
        method = message.get("method")
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Mcp-Session-Id", "session-1")
            self.end_headers()
            return
        if method == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {}}
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": "get_me"},
                    {"name": "search_repositories"},
                    {"name": "issue_read"},
                    {"name": "pull_request_read"},
                    {"name": "create_issue"},
                ]
            }
        elif method == "tools/call" and message["params"]["name"] == "get_me":
            result = {
                "content": [{"type": "text", "text": '{"login":"octocat"}'}]
            }
        else:
            result = {"content": [{"type": "text", "text": "listed"}]}
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "session-1")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_DELETE(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return


class GitHubChoiceTests(unittest.TestCase):
    def test_only_github_questions_are_routed(self):
        self.assertEqual(github_request("Who am I on GitHub?"), ("get_me", {}))
        self.assertEqual(
            github_request("GitHub issues in voicebot/app"),
            ("list_issues", {"owner": "voicebot", "repo": "app"}),
        )
        self.assertEqual(github_request("What is the capital of Japan?"), ("", {}))

    def test_headers_are_read_only_and_keep_the_token_out_of_the_url(self):
        headers = github_headers("secret-token")
        self.assertEqual(headers["X-MCP-Readonly"], "true")
        self.assertEqual(headers["X-MCP-Tools"], "get_me")
        self.assertEqual(
            headers["X-MCP-Toolsets"],
            "repos,issues,pull_requests,users",
        )
        self.assertEqual(headers["Authorization"], "Bearer secret-token")
        self.assertNotIn("secret-token", "https://api.githubcopilot.com/mcp/")

    def test_a_missing_token_does_not_call_the_server(self):
        github = GitHub(_settings("http://127.0.0.1:9/", token=""))
        self.assertEqual(github.call("get_me", {}), MISSING)

    def test_write_tools_are_refused(self):
        github = GitHub(_settings("http://127.0.0.1:9/"))
        github.tool_names = {"get_me", "create_issue"}
        github.client = object()
        self.assertEqual(github._tool("create_issue", {}), NOT_ALLOWED)


class RemoteClientTests(unittest.TestCase):
    def test_stream_body_parses_one_json_event(self):
        raw = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n'
        messages = parse_http_body(raw, "text/event-stream")
        self.assertEqual(messages[0]["id"], 1)

    def test_remote_get_me_uses_the_read_only_headers(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.seen_headers = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            github = GitHub(_settings(url))
            text = github.call("get_me", {})
            self.assertIn("octocat", text)
            sent = {key.lower(): value for key, value in server.seen_headers[0].items()}
            self.assertEqual(sent["x-mcp-readonly"], "true")
            self.assertEqual(sent["authorization"], "Bearer test-token")
            later = {key.lower(): value for key, value in server.seen_headers[-1].items()}
            self.assertEqual(later.get("mcp-session-id"), "session-1")
        finally:
            server.shutdown()
            github.close()


class GitHubGraphTests(unittest.TestCase):
    def test_who_am_i_calls_github_once(self):
        github = FakeGitHub()
        graph = build_graph(SummaryModel(), Conversation(), github=github)
        result = graph.invoke(empty_state("Who am I on GitHub?"))
        self.assertEqual(github.calls, [("get_me", {})])
        self.assertEqual(result["response"], "You are octocat on GitHub.")

    def test_a_fact_does_not_call_github(self):
        github = FakeGitHub()
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(FakeLLM(message), Conversation(), github=github)
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(github.calls, [])
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")


class RepoListTests(unittest.TestCase):
    def test_names_and_total_come_from_the_payload(self):
        payload = json.dumps(
            {
                "total_count": 16,
                "items": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            }
        )
        total, names = repo_names_from_tool_text(payload)
        self.assertEqual(total, 16)
        self.assertEqual(names, ["a", "b", "c"])

    def test_bad_payload_lists_nothing(self):
        self.assertEqual(repo_names_from_tool_text("not json"), (0, []))

    def test_repo_list_speaks_every_fetched_name(self):
        class ReposGitHub:
            def call(self, action, arguments):
                return json.dumps(
                    {
                        "total_count": 6,
                        "items": [{"name": f"repo-{index}"} for index in range(5)],
                    }
                )

        graph = build_graph(FakeLLM(FakeMessage("unused")), Conversation())
        from app.graph.workflow import _answer_from_github

        spoken = _answer_from_github(
            ReposGitHub(), FakeLLM(FakeMessage("unused")), "List my GitHub repos",
            "list_my_repos", {},
        )
        for index in range(5):
            self.assertIn(f"repo-{index}", spoken)
        self.assertIn("6", spoken)
