import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.config.settings import load_settings
from app.speech.devices import choose_device, microphone_inputs
from app.speech.listen import downmix, forward_heard, listen_once
from app.speech.transcribe import (
    MicrophoneUnavailable,
    WhisperUnavailable,
    to_whisper_rate,
    transcribe,
)


class Segment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, segments=None, error=None):
        self.segments = segments or []
        self.error = error
        self.calls = 0

    def transcribe(
        self,
        audio,
        language=None,
        beam_size=1,
        vad_filter=True,
        vad_parameters=None,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
    ):
        self.calls += 1
        self.audio = audio
        self.language = language
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.vad_parameters = vad_parameters
        if self.error:
            raise self.error
        return self.segments, None


class SettingsTests(unittest.TestCase):
    def test_whisper_model_comes_from_env(self):
        with patch.dict("os.environ", {"WHISPER_MODEL": "small"}, clear=False):
            settings = load_settings()
        self.assertEqual(settings.whisper_model, "small")
        self.assertEqual(settings.whisper_device, "cpu")


class AudioTests(unittest.TestCase):
    def test_resample_to_whisper_rate(self):
        audio = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32)
        converted = to_whisper_rate(audio, source_rate=8000, target_rate=16000)
        self.assertEqual(len(converted), 8)
        self.assertEqual(converted.dtype, np.float32)

    def test_stereo_is_mixed_to_mono(self):
        stereo = np.array([[0.0, 1.0], [1.0, 1.0]], dtype=np.float32)
        mixed = downmix(stereo)
        self.assertEqual(len(mixed), 2)
        self.assertAlmostEqual(float(mixed[0]), 0.5)

    def test_same_rate_is_unchanged_in_length(self):
        audio = np.ones(16000, dtype=np.float32)
        converted = to_whisper_rate(audio, 16000, 16000)
        self.assertEqual(len(converted), 16000)


class TranscribeTests(unittest.TestCase):
    def test_joins_segments(self):
        model = FakeModel([Segment(" what time "), Segment("is it")])
        text, elapsed = transcribe(model, np.zeros(16000), "en")
        self.assertEqual(text, "what time is it")
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual(model.language, "en")
        self.assertTrue(model.vad_filter)
        self.assertEqual(
            model.vad_parameters, {"min_silence_duration_ms": 800}
        )

    def test_short_silence_returns_empty_without_a_model_call(self):
        model = FakeModel([Segment("hello")])
        text, elapsed = transcribe(model, np.zeros(0, dtype=np.float32), "en")
        self.assertEqual(text, "")
        self.assertEqual(model.calls, 0)
        self.assertGreaterEqual(elapsed, 0)

    def test_failure_is_reported(self):
        model = FakeModel(error=RuntimeError("boom"))
        with self.assertRaises(WhisperUnavailable):
            transcribe(model, np.zeros(10), "en")


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.hostapis = [{"name": "MME"}, {"name": "Windows WASAPI"}]
        self.devices = [
            {
                "name": "Headphones (Realtek Audio)",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
            },
            {
                "name": "Microphone Array (Realtek Audio)",
                "hostapi": 0,
                "max_input_channels": 2,
                "max_output_channels": 0,
            },
            {
                "name": "Speakers (Realtek Audio)",
                "hostapi": 0,
                "max_input_channels": 0,
                "max_output_channels": 2,
            },
            {
                "name": "Microphone Array (Realtek Audio)",
                "hostapi": 1,
                "max_input_channels": 2,
                "max_output_channels": 0,
            },
            {
                "name": "Microphone (Headset)",
                "hostapi": 0,
                "max_input_channels": 1,
                "max_output_channels": 0,
            },
        ]

    def test_connected_headphones_are_chosen(self):
        from app.speech.devices import playback_kind

        self.assertEqual(
            playback_kind(
                ["Speakers (Realtek Audio)", "Headphones (Realtek Audio)"]
            ),
            "headphones",
        )

    def test_speakers_are_used_when_headphones_are_absent(self):
        from app.speech.devices import playback_kind

        self.assertEqual(playback_kind(["Speakers (Realtek Audio)"]), "speakers")

    def test_laptop_speakers_can_be_selected(self):
        index, name = choose_device(
            self.devices, self.hostapis, "speakers", False
        )
        self.assertEqual(index, 2)
        self.assertIn("Speakers", name)

    def test_built_in_and_headset_mics_are_both_used(self):
        mics = microphone_inputs(self.devices, self.hostapis)
        self.assertEqual(
            [name for _index, name in mics],
            [
                "Microphone Array (Realtek Audio)",
                "Microphone (Headset)",
            ],
        )


class ListenTests(unittest.TestCase):
    def test_listen_once_returns_text_and_times(self):
        settings = SimpleNamespace(record_seconds=5, whisper_language="en")
        model = FakeModel([Segment("hello")])

        def record(seconds):
            self.assertEqual(seconds, 5)
            return np.zeros(16000, dtype=np.float32), 5.0

        result = listen_once(settings, model, record)
        self.assertEqual(result["text"], "hello")
        self.assertEqual(result["capture_seconds"], 5.0)
        self.assertGreaterEqual(result["stt_seconds"], 0)

    def test_microphone_error_can_be_retried(self):
        settings = SimpleNamespace(record_seconds=5, whisper_language="en")
        calls = {"n": 0}

        def record(seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MicrophoneUnavailable("The microphone is not available.")
            return np.zeros(16000, dtype=np.float32), 0.1

        model = FakeModel([Segment("again")])
        with self.assertRaises(MicrophoneUnavailable):
            listen_once(settings, model, record)
        result = listen_once(settings, model, record)
        self.assertEqual(result["text"], "again")


class ForwardTests(unittest.TestCase):
    def test_silence_does_not_call_the_agent(self):
        class Session:
            def ask(self, text):
                raise AssertionError(text)

        self.assertIsNone(forward_heard(Session(), {"text": "  "}))

    def test_transcript_is_sent_to_the_agent(self):
        class Session:
            def ask(self, text):
                self.text = text
                return {"response": "It's 9 PM.", "should_exit": False}

        session = Session()
        answer = forward_heard(session, {"text": " What time is it? "})
        self.assertEqual(session.text, "What time is it?")
        self.assertEqual(answer["response"], "It's 9 PM.")


if __name__ == "__main__":
    unittest.main()
