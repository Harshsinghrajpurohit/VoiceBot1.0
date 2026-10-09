import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import _split_requests, build_graph, empty_state
from tests.test_phase2 import FakeLLM, FakeMessage


class SummaryModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return FakeMessage("Combined answer.")


class FakeSearch:
    def __init__(self):
        self.queries = []

    def call(self, query):
        self.queries.append(query)
        return "Pune is 31 degrees and clear."


class FakeGitHub:
    def __init__(self):
        self.calls = []

    def call(self, action, arguments):
        self.calls.append((action, arguments))
        return '{"login":"octocat"}'


class SplitTests(unittest.TestCase):
    def test_and_splits_into_two_parts(self):
        parts = _split_requests("What is the weather in Pune and who am I on GitHub?")
        self.assertEqual(len(parts), 2)

    def test_single_request_does_not_split(self):
        self.assertEqual(len(_split_requests("What is the capital of Japan?")), 1)


class MultiToolTests(unittest.TestCase):
    def test_two_independent_tools_run_together(self):
        search = FakeSearch()
        github = FakeGitHub()
        graph = build_graph(
            SummaryModel(), Conversation(), search=search, github=github
        )
        result = graph.invoke(
            empty_state("What is the weather in Pune and who am I on GitHub?")
        )
        self.assertEqual(search.queries, ["What is the weather in Pune"])
        self.assertEqual(github.calls, [("get_me", {})])
        self.assertEqual(result["response"], "Combined answer.")
        self.assertGreaterEqual(result["tool_seconds"], 0)

    def test_single_tool_keeps_its_old_path(self):
        search = FakeSearch()
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(
            FakeLLM(message), Conversation(), search=search, github=FakeGitHub()
        )
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(search.queries, [])
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")


if __name__ == "__main__":
    unittest.main()
