import sys
import unittest
from pathlib import Path

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.mcp.client import StdioClient
from app.mcp.playwright_server import (
    PlaywrightBrowser,
    needs_browser,
    resolve_page,
    trim_page,
)
from tests.test_phase2 import FakeLLM, FakeMessage


class SummaryModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        return FakeMessage("The page is Example Domain.")


class FakeBrowser:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "browser_snapshot":
            return "heading Example Domain"
        return "opened"


class BrowserChoiceTests(unittest.TestCase):
    def test_only_a_url_uses_the_browser(self):
        self.assertTrue(needs_browser("Open https://example.com"))
        self.assertFalse(needs_browser("What is the capital of Japan?"))

    def test_common_names_resolve_without_a_url(self):
        self.assertEqual(resolve_page("Open Google"), "https://www.google.com")
        self.assertEqual(
            resolve_page("Open the Chrome browser"),
            "https://www.google.com",
        )
        self.assertEqual(resolve_page("Open YouTube"), "https://www.youtube.com")
        self.assertEqual(resolve_page("Open Gmail"), "https://mail.google.com")
        self.assertEqual(
            resolve_page("Go to LinkedIn"),
            "https://www.linkedin.com",
        )
        self.assertEqual(
            resolve_page("Open the weather website"),
            "https://www.google.com/search?q=weather",
        )
        self.assertIn(
            "today%27s+weather",
            resolve_page("Search Google for today's weather"),
        )
        self.assertEqual(resolve_page("What is the capital of Japan?"), "")

    def test_page_text_is_shortened(self):
        self.assertEqual(len(trim_page("word " * 2000)), 1200)

    def test_unsafe_browser_tool_is_refused(self):
        browser = PlaywrightBrowser(object())
        self.assertEqual(
            browser.call("browser_evaluate", {"code": "1"}),
            "That tool is not available.",
        )
        self.assertIsNone(browser.client)


class GraphBrowserTests(unittest.TestCase):
    def test_url_reads_the_page_and_summarizes_it(self):
        browser = FakeBrowser()
        graph = build_graph(SummaryModel(), Conversation(), browser=browser)
        result = graph.invoke(empty_state("Open https://example.com"))
        self.assertEqual(result["response"], "The page is Example Domain.")
        self.assertEqual(
            browser.calls[0],
            ("browser_navigate", {"url": "https://example.com"}),
        )
        self.assertEqual(browser.calls[1][0], "browser_snapshot")

    def test_open_google_does_not_ask_the_model_for_a_url(self):
        browser = FakeBrowser()
        model = SummaryModel()
        graph = build_graph(model, Conversation(), browser=browser)
        result = graph.invoke(empty_state("Open Google"))
        self.assertEqual(
            browser.calls[0],
            ("browser_navigate", {"url": "https://www.google.com"}),
        )
        self.assertEqual(model.calls, 1)
        self.assertEqual(result["response"], "The page is Example Domain.")

    def test_fact_question_does_not_open_the_browser(self):
        browser = FakeBrowser()
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(FakeLLM(message), Conversation(), browser=browser)
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")
        self.assertEqual(browser.calls, [])

    def test_model_cannot_choose_a_page_code_tool(self):
        browser = FakeBrowser()
        message = FakeMessage(
            "The page is Example Domain.",
            tool_calls=[
                {
                    "name": "browser_evaluate",
                    "args": {"code": "alert(1)"},
                    "id": "1",
                }
            ],
        )
        graph = build_graph(FakeLLM(message), Conversation(), browser=browser)
        result = graph.invoke(empty_state("Open https://example.com"))
        self.assertEqual(
            browser.calls[0],
            ("browser_navigate", {"url": "https://example.com"}),
        )
        self.assertNotIn("browser_evaluate", [name for name, _args in browser.calls])
        self.assertEqual(result["response"], "The page is Example Domain.")


class ClientTests(unittest.TestCase):
    def test_fake_server_lists_and_calls_a_tool(self):
        script = Path(__file__).resolve().parent / "fake_mcp_server.py"
        client = StdioClient([sys.executable, str(script)])
        client.start()
        try:
            names = [tool["name"] for tool in client.list_tools()]
            self.assertIn("browser_navigate", names)
            text = client.call_tool(
                "browser_navigate",
                {"url": "https://example.com"},
            )
        finally:
            client.close()
        self.assertIn("https://example.com", text)


if __name__ == "__main__":
    unittest.main()
