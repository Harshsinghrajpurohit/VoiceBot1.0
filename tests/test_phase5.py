import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.config.settings import load_settings
from app.speech.speak import (
    PiperUnavailable,
    SpeakerUnavailable,
    deliver,
    speak,
    speak_answer,
    synthesize,
    voice_file,
)


class Chunk:
    def __init__(self, samples, sample_rate=22050):
        self.audio_float_array = np.asarray(samples, dtype=np.float32)
        self.sample_rate = sample_rate


class FakeVoice:
    def __init__(self, chunks=None, error=None):
        self.chunks = chunks or [Chunk([0.0, 0.2, -0.2])]
        self.error = error
        self.text = ""

    def synthesize(self, text):
        self.text = text
        if self.error:
            raise self.error
        for chunk in self.chunks:
            yield chunk


class SettingsTests(unittest.TestCase):
    def test_voice_comes_from_env(self):
        with patch.dict(
            "os.environ",
            {"PIPER_VOICE": "en_US-lessac-medium"},
            clear=False,
        ):
            settings = load_settings()
        self.assertEqual(settings.piper_voice, "en_US-lessac-medium")
        self.assertTrue(str(voice_file(settings)).endswith("en_US-lessac-medium.onnx"))


class SpeakTests(unittest.TestCase):
    def test_synthesize_joins_chunks(self):
        voice = FakeVoice([Chunk([0.1, 0.2]), Chunk([0.3])])
        audio, rate, elapsed = synthesize(voice, "Hello.")
        self.assertEqual(list(audio), [0.1, 0.2, 0.3])
        self.assertEqual(rate, 22050)
        self.assertGreaterEqual(elapsed, 0)

    def test_speak_plays_audio_and_records_time(self):
        voice = FakeVoice()
        played = {}

        def play(audio, sample_rate):
            played["samples"] = len(audio)
            played["rate"] = sample_rate
            return 0.25

        timing = speak(voice, " The answer is 391. ", play)
        self.assertEqual(voice.text, "The answer is 391.")
        self.assertEqual(played["samples"], 3)
        self.assertEqual(played["rate"], 22050)
        self.assertEqual(timing["playback_seconds"], 0.25)
        self.assertGreaterEqual(timing["tts_seconds"], 0)

    def test_blank_text_does_not_speak(self):
        voice = FakeVoice()
        timing = speak(voice, "  ", lambda audio, rate: 1)
        self.assertEqual(timing["tts_seconds"], 0.0)
        self.assertEqual(voice.text, "")

    def test_synthesis_failure(self):
        voice = FakeVoice(error=RuntimeError("boom"))
        with self.assertRaises(PiperUnavailable):
            synthesize(voice, "Hello.")

    def test_speaker_failure_still_returns_after_print(self):
        voice = FakeVoice()

        def play(audio, sample_rate):
            raise SpeakerUnavailable("The speaker is not available.")

        with patch("builtins.print") as printed:
            timing = speak_answer(voice, "Hello.", play)
        self.assertIsNone(timing)
        self.assertEqual(
            str(printed.call_args.args[0]),
            "The speaker is not available.",
        )

    def test_spoken_reply_is_not_printed(self):
        voice = FakeVoice()
        with patch("builtins.print") as printed:
            timing = deliver(voice, "The answer is 391.", lambda audio, rate: 0.1)
        self.assertIsNotNone(timing)
        printed.assert_not_called()

    def test_unspoken_reply_is_printed(self):
        with patch("builtins.print") as printed:
            timing = deliver(None, "The answer is 391.")
        self.assertIsNone(timing)
        printed.assert_called_with("The answer is 391.")


if __name__ == "__main__":
    unittest.main()
