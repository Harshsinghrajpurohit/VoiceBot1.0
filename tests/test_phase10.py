import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from tests.test_phase2 import FakeLLM, FakeMessage


class FakeSearch:
    """One canned web answer. Understands current-information questions."""

    def call(self, query):
        return f"web: {query}"


class FakeBrowser:
    """One canned page read. Understands open-the-page requests."""

    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "browser_snapshot":
            return "heading Example Domain"
        return "opened"


class WebBrowserSeparationTests(unittest.TestCase):
    def test_search_and_browser_stay_separate(self):
        search = FakeSearch()
        browser = FakeBrowser()
        model = FakeLLM(FakeMessage("Nothing for a fact question."))
        graph = build_graph(model, Conversation(), browser=browser, search=search)
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(result["response"], "Nothing for a fact question.")
        self.assertEqual(browser.calls, [])

    def test_open_uses_browser_not_search_results(self):
        search = FakeSearch()

        class SummaryModel:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                return FakeMessage("The page is Example Domain.")

        graph = build_graph(
            SummaryModel(), Conversation(), browser=FakeBrowser(), search=search
        )
        result = graph.invoke(empty_state("Open https://example.com"))
        self.assertEqual(result["response"], "The page is Example Domain.")

    def test_no_browser_keeps_search_alone(self):
        search = FakeSearch()
        model = FakeLLM(FakeMessage("Nothing for a fact question."))
        graph = build_graph(model, Conversation(), search=search)
        result = graph.invoke(empty_state("Open https://example.com"))
        self.assertEqual(result["response"], "Nothing for a fact question.")


if __name__ == "__main__":
    unittest.main()
