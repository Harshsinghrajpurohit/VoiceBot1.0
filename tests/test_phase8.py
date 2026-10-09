import os
import tempfile
import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.memory.store import (
    ASK_DELETE,
    CONFIRM,
    DELETED,
    EMPTY,
    FORGOT,
    REMEMBERED,
    MemoryStore,
)
from tests.test_phase2 import FakeLLM, FakeMessage


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.store = MemoryStore(os.path.join(folder, "memory.json"))

    def test_remember_forget_and_inspect(self):
        self.assertEqual(self.store.respond("Remember that my name is Ada"), REMEMBERED)
        self.assertEqual(self.store.records[0]["kind"], "fact")
        self.assertIn("name is Ada", self.store.respond("What do you remember about me?"))
        self.assertEqual(self.store.respond("Remember that I prefer short answers"), REMEMBERED)
        self.assertEqual(self.store.records[-1]["kind"], "preference")
        self.assertEqual(self.store.respond("Forget that my name is Ada"), FORGOT)
        self.assertEqual(len(self.store.records), 1)

    def test_delete_everything_waits_for_confirmation(self):
        self.store.respond("Remember that I like tea")
        self.assertEqual(
            self.store.respond("Delete everything you remember about me"),
            ASK_DELETE,
        )
        self.assertEqual(len(self.store.records), 1)
        self.assertEqual(self.store.respond(CONFIRM), DELETED)
        self.assertEqual(self.store.records, [])
        self.assertEqual(self.store.respond("What do you remember?"), EMPTY)

    def test_confirmation_without_a_request_does_not_delete(self):
        self.store.respond("Remember that I like tea")
        self.assertIsNone(self.store.respond(CONFIRM))
        self.assertEqual(len(self.store.records), 1)

    def test_a_normal_question_is_not_memory(self):
        self.assertIsNone(self.store.respond("What is the capital of Japan?"))


class MemoryGraphTests(unittest.TestCase):
    def test_remember_does_not_call_the_model(self):
        folder = tempfile.mkdtemp()
        memory = MemoryStore(os.path.join(folder, "memory.json"))
        message = FakeMessage("This should not be spoken.")
        graph = build_graph(FakeLLM(message), Conversation(), memory=memory)
        result = graph.invoke(empty_state("Remember that my name is Ada"))
        self.assertEqual(result["response"], REMEMBERED)
        self.assertEqual(result["llm_seconds"], 0.0)
