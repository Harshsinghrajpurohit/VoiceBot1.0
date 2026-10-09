import unittest
from types import SimpleNamespace

from app.speech.loop import voice_turn
from app.speech.transcribe import MicrophoneUnavailable


class FakeSession:
    def __init__(self, response="Tokyo.", should_exit=False):
        self.asked = []
        self.response = response
        self.should_exit = should_exit

    def ask(self, text):
        self.asked.append(text)
        return {
            "response": self.response,
            "should_exit": self.should_exit,
            "intent_seconds": 0.0,
            "llm_seconds": 0.1,
            "tool_seconds": 0.0,
        }


class LoopTests(unittest.TestCase):
    def test_heard_speech_is_answered_and_spoken(self):
        settings = SimpleNamespace()
        session = FakeSession()
        spoken = []

        def listen(settings, model):
            return {
                "text": " What is the capital of Japan? ",
                "capture_seconds": 5.0,
                "stt_seconds": 2.0,
            }

        def speak(voice, text):
            spoken.append(text)
            return {"tts_seconds": 0.2, "playback_seconds": 1.5}

        turn = voice_turn(settings, None, object(), session, listen, speak)
        self.assertEqual(session.asked, ["What is the capital of Japan?"])
        self.assertEqual(spoken, ["Tokyo."])
        self.assertTrue(turn["ok"])
        self.assertFalse(turn["should_exit"])

    def test_silence_does_not_call_the_agent(self):
        session = FakeSession()
        spoken = []

        def listen(settings, model):
            return {"text": "  ", "capture_seconds": 5.0, "stt_seconds": 1.0}

        turn = voice_turn(
            SimpleNamespace(),
            None,
            object(),
            session,
            listen,
            lambda voice, text: spoken.append(text),
        )
        self.assertEqual(session.asked, [])
        self.assertEqual(spoken, [])
        self.assertEqual(turn["heard"], "")

    def test_microphone_failure_can_be_tried_again(self):
        def listen(settings, model):
            raise MicrophoneUnavailable("The microphone is not available.")

        turn = voice_turn(
            SimpleNamespace(),
            None,
            object(),
            FakeSession(),
            listen,
            lambda voice, text: None,
        )
        self.assertFalse(turn["ok"])
        self.assertIn("microphone", turn["error"])

    def test_exit_ends_the_loop(self):
        session = FakeSession("Goodbye.", should_exit=True)

        def listen(settings, model):
            return {"text": "exit", "capture_seconds": 1.0, "stt_seconds": 0.2}

        turn = voice_turn(
            SimpleNamespace(),
            None,
            object(),
            session,
            listen,
            lambda voice, text: {"tts_seconds": 0.1, "playback_seconds": 0.5},
        )
        self.assertTrue(turn["should_exit"])
        self.assertEqual(session.asked, ["exit"])


if __name__ == "__main__":
    unittest.main()
