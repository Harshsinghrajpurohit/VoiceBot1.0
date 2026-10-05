import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app.config.settings import load_settings
from app.graph.workflow import build_graph
from app.llm.client import (
    ModelUnavailable,
    OllamaUnavailable,
    ensure_model,
    list_models,
)


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def invoke(self, messages):
        self.messages = messages
        return FakeMessage("Hello.")


class SettingsTests(unittest.TestCase):
    def test_model_comes_from_env(self):
        with patch.dict(
            "os.environ",
            {"OLLAMA_MODEL": "llama3.2:latest"},
            clear=False,
        ):
            settings = load_settings()
        self.assertEqual(settings.ollama_model, "llama3.2:latest")


class OllamaCheckTests(unittest.TestCase):
    def test_ollama_down(self):
        error = urllib.error.URLError("refused")
        with patch("app.llm.client.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(OllamaUnavailable):
                list_models("http://127.0.0.1:11434", 1)

    def test_missing_model(self):
        payload = json.dumps({"models": [{"name": "other:latest"}]}).encode()

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        response = FakeResponse(payload)
        settings = load_settings()
        with patch("app.llm.client.urllib.request.urlopen", return_value=response):
            with self.assertRaises(ModelUnavailable):
                ensure_model(settings)


class GraphTests(unittest.TestCase):
    def test_generate_returns_model_text(self):
        graph = build_graph(FakeLLM())
        result = graph.invoke(
            {
                "user_input": "Say hello.",
                "response": "",
                "llm_seconds": 0.0,
            }
        )
        self.assertEqual(result["response"], "Hello.")
        self.assertGreaterEqual(result["llm_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
