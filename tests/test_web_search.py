import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.mcp.search_server import format_results
from app.mcp.web_search import search_query
from tests.test_phase2 import FakeLLM, FakeMessage


PAGE = """
<a class='result-link'>Pune Weather</a>
<td class='result-snippet'>It is <b>31 degrees</b> and clear.</td>
<a class='result-link'>Other</a>
<td class='result-snippet'>Ignore this extra result.</td>
"""


class SummaryModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return FakeMessage("It is 31 degrees and clear in Pune.")


class FakeSearch:
    def __init__(self):
        self.queries = []

    def call(self, query):
        self.queries.append(query)
        return "Pune is 31 degrees and clear."


class SearchChoiceTests(unittest.TestCase):
    def test_current_questions_search_and_facts_do_not(self):
        self.assertEqual(search_query("What is the weather in Pune?"), "What is the weather in Pune")
        self.assertEqual(search_query("Search for today's weather"), "today's weather")
        self.assertEqual(search_query("What is the capital of Japan?"), "")

    def test_results_keep_the_title_and_snippet(self):
        text = format_results(PAGE, limit=1)
        self.assertEqual(text, "Pune Weather. It is 31 degrees and clear.")


class SearchGraphTests(unittest.TestCase):
    def test_weather_uses_search_then_one_summary(self):
        search = FakeSearch()
        graph = build_graph(SummaryModel(), Conversation(), search=search)
        result = graph.invoke(empty_state("What is the weather in Pune?"))
        self.assertEqual(search.queries, ["What is the weather in Pune"])
        self.assertEqual(result["response"], "It is 31 degrees and clear in Pune.")

    def test_fact_question_does_not_search(self):
        search = FakeSearch()
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(FakeLLM(message), Conversation(), search=search)
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(search.queries, [])
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")
