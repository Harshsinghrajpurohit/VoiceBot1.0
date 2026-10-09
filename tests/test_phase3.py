import unittest
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.measure.baseline import format_report
from app.measure.resources import parse_gpu_line
from app.measure.usage import generation_stats, prompt_chars
from tests.test_phase2 import FakeLLM, FakeMessage


class UsageTests(unittest.TestCase):
    def test_prompt_chars_counts_message_text(self):
        messages = [
            SystemMessage(content="Hello"),
            HumanMessage(content="time"),
        ]
        self.assertEqual(prompt_chars(messages), 9)

    def test_generation_speed_uses_eval_duration(self):
        message = SimpleNamespace(
            response_metadata={
                "prompt_eval_count": 20,
                "eval_count": 10,
                "eval_duration": 500_000_000,
                "load_duration": 2_000_000_000,
            },
            usage_metadata={},
        )
        stats = generation_stats(message, 3.0)
        self.assertEqual(stats["prompt_tokens"], 20)
        self.assertEqual(stats["output_tokens"], 10)
        self.assertAlmostEqual(stats["tokens_per_second"], 20.0)
        self.assertAlmostEqual(stats["load_seconds"], 2.0)

    def test_missing_metadata_is_zero(self):
        stats = generation_stats(SimpleNamespace(), 1.0)
        self.assertEqual(stats["output_tokens"], 0)
        self.assertEqual(stats["tokens_per_second"], 0.0)


class ResourceTests(unittest.TestCase):
    def test_parse_gpu_line(self):
        parsed = parse_gpu_line("1843, 12, 4096")
        self.assertEqual(parsed["gpu_memory_mb"], 1843)
        self.assertEqual(parsed["gpu_util_percent"], 12)
        self.assertEqual(parsed["gpu_total_mb"], 4096)

    def test_bad_gpu_line(self):
        self.assertIsNone(parse_gpu_line("not a sample"))


class GraphMeasureTests(unittest.TestCase):
    def test_model_turn_records_prompt_size(self):
        message = FakeMessage("Hello.")
        message.response_metadata = {
            "prompt_eval_count": 12,
            "eval_count": 4,
            "eval_duration": 200_000_000,
        }
        llm = FakeLLM(message)
        graph = build_graph(llm, Conversation())
        result = graph.invoke(empty_state("Say hello."))
        self.assertGreater(result["prompt_chars"], 0)
        self.assertEqual(result["prompt_tokens"], 12)
        self.assertEqual(result["output_tokens"], 4)
        self.assertAlmostEqual(result["tokens_per_second"], 20.0)

    def test_fast_path_records_zeros(self):
        graph = build_graph(FakeLLM(FakeMessage("no")), Conversation())
        result = graph.invoke(empty_state("What time is it?"))
        self.assertEqual(result["prompt_chars"], 0)
        self.assertEqual(result["output_tokens"], 0)
        self.assertEqual(result["llm_seconds"], 0.0)


class ReportTests(unittest.TestCase):
    def test_report_includes_the_measurement(self):
        settings = SimpleNamespace(
            ollama_model="llama3.2:latest",
            num_ctx=2048,
            num_predict=128,
        )
        rows = [
            {
                "request": "What time is it?",
                "kind": "fast",
                "intent_seconds": 0.001,
                "llm_seconds": 0.0,
                "tool_seconds": 0.0,
                "load_seconds": 0.0,
                "prompt_chars": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "tokens_per_second": 0.0,
                "process_mb": 40.0,
                "system_used_mb": 6000.0,
            }
        ]
        report = format_report(settings, rows, ["System RAM: 8000 MB."])
        self.assertIn("llama3.2:latest", report)
        self.assertIn("What time is it?", report)
        self.assertIn("System RAM: 8000 MB.", report)


if __name__ == "__main__":
    unittest.main()
