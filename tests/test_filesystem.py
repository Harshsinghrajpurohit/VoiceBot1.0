import os
import tempfile
import unittest

from app.agent.conversation import Conversation
from app.graph.workflow import build_graph, empty_state
from app.mcp.filesystem import REFUSED, filesystem_request
from tests.test_phase2 import FakeLLM, FakeMessage


class SummaryModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return FakeMessage("Documents has notes.")


class FakeFiles:
    def __init__(self, root: str):
        self.root = root
        self.calls = []

    def roots(self):
        return [self.root]

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return "[FILE] notes.txt"


class FilesystemChoiceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.notes = os.path.join(self.root, "notes.txt")
        with open(self.notes, "w", encoding="utf-8") as handle:
            handle.write("hello")

    def test_list_and_read_stay_inside_the_folder(self):
        kind, args = filesystem_request("list files", [self.root])
        self.assertEqual(kind, "list_directory")
        self.assertEqual(args["path"], os.path.realpath(self.root))
        kind, args = filesystem_request("read the file notes.txt", [self.root])
        self.assertEqual(kind, "read_text_file")
        self.assertEqual(args["path"], os.path.realpath(self.notes))
        self.assertEqual(args["head"], 40)

    def test_a_path_outside_the_folder_is_refused(self):
        kind, _args = filesystem_request(
            "read the file ..\\..\\Windows\\notepad.exe",
            [self.root],
        )
        self.assertEqual(kind, "missing")

    def test_changes_are_not_run(self):
        kind, _args = filesystem_request("delete the file notes.txt", [self.root])
        self.assertEqual(kind, "refused")

    def test_a_fact_is_not_a_file_request(self):
        kind, _args = filesystem_request("What is the capital of Japan?", [self.root])
        self.assertEqual(kind, "")


class FilesystemGraphTests(unittest.TestCase):
    def test_list_files_reads_the_directory(self):
        root = tempfile.mkdtemp()
        files = FakeFiles(root)
        graph = build_graph(SummaryModel(), Conversation(), files=files)
        result = graph.invoke(empty_state("list files"))
        self.assertEqual(files.calls[0][0], "list_directory")
        self.assertEqual(result["response"], "Documents has notes.")

    def test_delete_does_not_call_the_server(self):
        root = tempfile.mkdtemp()
        files = FakeFiles(root)
        graph = build_graph(SummaryModel(), Conversation(), files=files)
        result = graph.invoke(empty_state("delete the file notes.txt"))
        self.assertEqual(files.calls, [])
        self.assertEqual(result["response"], REFUSED)

    def test_fact_question_does_not_list_files(self):
        root = tempfile.mkdtemp()
        files = FakeFiles(root)
        message = FakeMessage("Tokyo is the capital of Japan.")
        graph = build_graph(FakeLLM(message), Conversation(), files=files)
        result = graph.invoke(empty_state("What is the capital of Japan?"))
        self.assertEqual(files.calls, [])
        self.assertEqual(result["response"], "Tokyo is the capital of Japan.")
