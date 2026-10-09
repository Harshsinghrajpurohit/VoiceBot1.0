import unittest

import numpy as np

from app.speech.listen import trailing_silence, voice_active
from app.speech.speak import split_sentences, speak


class VoiceActivityTests(unittest.TestCase):
    def test_loud_chunk_is_speech(self):
        self.assertTrue(voice_active(np.full(1600, 0.1, dtype=np.float32)))

    def test_room_silence_is_not_speech(self):
        self.assertFalse(voice_active(np.zeros(1600, dtype=np.float32)))

    def test_quiet_tail_is_measured(self):
        speech = np.full(16000, 0.1, dtype=np.float32)
        quiet = np.zeros(16000, dtype=np.float32)
        heard = np.concatenate([speech, quiet])
        self.assertGreaterEqual(trailing_silence(heard, 16000), 0.7)

    def test_speech_at_the_end_has_no_trailing_silence(self):
        quiet = np.zeros(16000, dtype=np.float32)
        speech = np.full(16000, 0.1, dtype=np.float32)
        heard = np.concatenate([quiet, speech])
        self.assertEqual(trailing_silence(heard, 16000), 0.0)

    def test_edges_are_trimmed_before_whisper(self):
        from app.speech.listen import trim_edges

        speech = np.full(16000, 0.1, dtype=np.float32)
        heard = np.concatenate(
            [np.zeros(16000, dtype=np.float32), speech, np.zeros(8000, dtype=np.float32)]
        )
        trimmed = trim_edges(heard, 16000, 0.008)
        self.assertLess(len(trimmed), len(heard))
        self.assertGreaterEqual(len(trimmed) / 16000, 0.4)

    def test_all_silence_trims_to_nothing(self):
        from app.speech.listen import trim_edges

        trimmed = trim_edges(np.zeros(16000, dtype=np.float32), 16000, 0.008)
        self.assertEqual(len(trimmed), 1)


class SentenceSpeechTests(unittest.TestCase):
    def test_short_reply_stays_whole(self):
        self.assertEqual(split_sentences("The answer is 391."), ["The answer is 391."])

    def test_two_sentences_split_for_first_audio(self):
        self.assertEqual(
            split_sentences("It is four thirty. The answer is 391."),
            ["It is four thirty.", "The answer is 391."],
        )

    def test_blank_text_has_no_first_audio(self):
        timing = speak(object(), "  ", lambda audio, rate: 1)
        self.assertEqual(timing["first_audio_seconds"], 0.0)

    def test_first_sentence_is_ready_before_the_second(self):
        import tests.test_phase5 as phase5

        voice = phase5.FakeVoice()
        played = []

        def play(audio, sample_rate):
            played.append(len(audio))
            return 0.1

        timing = speak(voice, "First. Second.", play)
        self.assertEqual(voice.text, "Second.")
        self.assertEqual(len(played), 2)
        self.assertGreater(timing["first_audio_seconds"], 0.0)
        self.assertGreaterEqual(timing["tts_seconds"], 0.0)
        self.assertGreaterEqual(timing["playback_seconds"], 0.2)


if __name__ == "__main__":
    unittest.main()
