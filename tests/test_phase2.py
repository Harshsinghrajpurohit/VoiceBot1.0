import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.tools.calculator import calculate, needs_calculator


class FakeMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeLLM:
    def __init__(self, message):
        self.message = message
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls += 1
        self.messages = messages
        return self.message


class FastPathTests(unittest.TestCase):
    def test_time_skips_the_model(self):
        llm = FakeLLM(FakeMessage("should not be used"))
        graph = build_graph(llm, Conversation())
        result = graph.invoke(empty_state("What time is it?"))
        self.assertEqual(llm.calls, 0)
        self.assertTrue(result["response"].startswith("It's "))
        self.assertEqual(result["llm_seconds"], 0.0)

    def test_date_skips_the_model(self):
        llm = FakeLLM(FakeMessage("should not be used"))
        graph = build_graph(llm, Conversation())
        result = graph.invoke(empty_state("What's today's date?"))
        self.assertEqual(llm.calls, 0)
        self.assertTrue(result["response"].startswith("Today is "))

    def test_repeat_and_clear(self):
        conversation = Conversation()
        llm = FakeLLM(FakeMessage("Hello."))
        graph = build_graph(llm, conversation)
        first = graph.invoke(empty_state("Say hello."))
        self.assertEqual(first["response"], "Hello.")
        again = graph.invoke(empty_state("Repeat that."))
        self.assertEqual(again["response"], "Hello.")
        self.assertEqual(llm.calls, 1)
        cleared = graph.invoke(empty_state("Clear conversation."))
        self.assertEqual(cleared["response"], "Conversation cleared.")
        self.assertEqual(conversation.turns, [])
        empty = graph.invoke(empty_state("Repeat that."))
        self.assertEqual(empty["response"], "I have nothing to repeat.")

    def test_exit(self):
        graph = build_graph(FakeLLM(FakeMessage("no")), Conversation())
        result = graph.invoke(empty_state("exit"))
        self.assertEqual(result["response"], "Goodbye.")
        self.assertTrue(result["should_exit"])


class ToolTests(unittest.TestCase):
    def test_calculator_runs_once(self):
        message = FakeMessage(
            tool_calls=[
                {
                    "name": "calculator",
                    "args": {"expression": "17*23"},
                    "id": "1",
                }
            ]
        )
        llm = FakeLLM(message)
        graph = build_graph(llm, Conversation())
        result = graph.invoke(empty_state("What is 17 times 23?"))
        self.assertEqual(llm.calls, 1)
        self.assertEqual(result["response"], "The answer is 391.")
        self.assertGreaterEqual(result["tool_seconds"], 0)

    def test_calculator_written_as_text_still_runs(self):
        message = FakeMessage(
            '{"name":"calculator","parameters":{"expression":"17 * 23"}}'
        )
        graph = build_graph(FakeLLM(message), Conversation())
        result = graph.invoke(empty_state("What is 17 times 23?"))
        self.assertEqual(result["response"], "The answer is 391.")

    def test_unknown_tool(self):
        message = FakeMessage(
            tool_calls=[{"name": "delete_file", "args": {}, "id": "1"}]
        )
        graph = build_graph(FakeLLM(message), Conversation())
        result = graph.invoke(empty_state("What is 2 + 2?"))
        self.assertEqual(result["response"], "That tool is not available.")

    def test_fact_question_is_not_sent_to_the_calculator(self):
        message = FakeMessage(
            "Tokyo is the capital of Japan.",
            tool_calls=[
                {
                    "name": "calculator",
                    "args": {"expression": "japan"},
                    "id": "1",
                }
            ],
        )
        graph = build_graph(FakeLLM(message), Conversation())
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")

    def test_bad_expression_asks_the_model_instead(self):
        class TwoStep:
            def __init__(self):
                self.calls = 0

            def bind_tools(self, tools):
                return self

            def invoke(self, messages):
                self.calls += 1
                if self.calls == 1:
                    return FakeMessage(
                        tool_calls=[
                            {
                                "name": "calculator",
                                "args": {"expression": "capital of japan"},
                                "id": "1",
                            }
                        ]
                    )
                return FakeMessage("Tokyo is the capital of Japan.")

        llm = TwoStep()
        graph = build_graph(llm, Conversation())
        result = graph.invoke(empty_state("What is 2 + japan?"))
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")
        self.assertEqual(llm.calls, 2)

    def test_bad_expression_is_rejected(self):
        self.assertEqual(
            calculate("__import__('os')"),
            "That calculation is not allowed.",
        )
        self.assertEqual(calculate("1/0"), "I can't divide by zero.")
        self.assertFalse(needs_calculator("What is the capital of Japan?"))
        self.assertTrue(needs_calculator("What is 17 times 23?"))


class ModelDownTests(unittest.TestCase):
    def test_time_still_works(self):
        graph = build_graph(None, Conversation(), "Ollama is not reachable.")
        result = graph.invoke(empty_state("What time is it?"))
        self.assertTrue(result["response"].startswith("It's "))

    def test_other_requests_report_the_error(self):
        graph = build_graph(None, Conversation(), "Ollama is not reachable.")
        result = graph.invoke(empty_state("Tell me a joke."))
        self.assertEqual(result["response"], "Ollama is not reachable.")


if __name__ == "__main__":
    unittest.main()
