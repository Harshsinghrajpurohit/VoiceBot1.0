"""Text to speech. Piper synthesizes audio, sounddevice plays it."""

import re
import sys
import time
from pathlib import Path

import numpy as np

from app.speech.devices import resolve_output

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class PiperUnavailable(Exception):
    """Piper could not speak."""


class SpeakerUnavailable(Exception):
    """The speaker could not play audio."""


def voice_file(settings) -> Path:
    directory = Path(settings.piper_voice_dir)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    return directory / f"{settings.piper_voice}.onnx"


def load_voice(settings):
    try:
        from piper import PiperVoice
        from piper.download_voices import download_voice
    except ImportError as exc:
        raise PiperUnavailable("Piper is not installed.") from exc

    path = voice_file(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        download_voice(settings.piper_voice, path.parent)
        return PiperVoice.load(path, use_cuda=False)
    except Exception as exc:
        raise PiperUnavailable(
            f"Could not load Piper voice {settings.piper_voice}."
        ) from exc


def synthesize(voice, text: str):
    started = time.perf_counter()
    chunks = []
    sample_rate = 22050
    try:
        for chunk in voice.synthesize(text):
            chunks.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
            sample_rate = int(chunk.sample_rate)
    except Exception as exc:
        raise PiperUnavailable("Speech synthesis failed.") from exc
    if not chunks:
        return np.zeros(1, dtype=np.float32), sample_rate, time.perf_counter() - started
    return np.concatenate(chunks), sample_rate, time.perf_counter() - started


def play_audio(audio, sample_rate: int) -> float:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SpeakerUnavailable("Audio playback is not installed.") from exc

    started = time.perf_counter()
    try:
        device, name = resolve_output(sd)
        print(f"Speaking: {name}")
        sd.play(np.asarray(audio, dtype=np.float32), sample_rate, device=device)
        sd.wait()
    except Exception as exc:
        raise SpeakerUnavailable("The speaker is not available.") from exc
    return time.perf_counter() - started


def split_sentences(text: str) -> list[str]:
    """Split a reply into spoken sentences. Short replies stay whole."""
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    parts = [part.strip() for part in _SENTENCE_END.split(cleaned)]
    return [part for part in parts if part]


def speak(voice, text: str, play=play_audio) -> dict:
    cleaned = text.strip()
    if not cleaned:
        return {
            "tts_seconds": 0.0,
            "playback_seconds": 0.0,
            "first_audio_seconds": 0.0,
        }
    started = time.perf_counter()
    first_audio_seconds = 0.0
    tts_seconds = 0.0
    playback_seconds = 0.0
    for sentence in split_sentences(cleaned):
        audio, sample_rate, elapsed = synthesize(voice, sentence)
        tts_seconds += elapsed
        if first_audio_seconds == 0.0:
            first_audio_seconds = time.perf_counter() - started
        playback_seconds += play(audio, sample_rate)
    return {
        "tts_seconds": tts_seconds,
        "playback_seconds": playback_seconds,
        "first_audio_seconds": first_audio_seconds,
    }


def open_voice(settings):
    print(f"Loading Piper voice {settings.piper_voice}.")
    started = time.perf_counter()
    try:
        voice = load_voice(settings)
    except PiperUnavailable as exc:
        print(exc)
        print("Answers will be printed.")
        return None
    print(f"Voice load: {time.perf_counter() - started:.2f}s")
    return voice


def speak_answer(voice, text: str, play=play_audio) -> dict | None:
    """Speak text. Returns None when nothing was spoken."""
    if voice is None or not text.strip():
        return None
    try:
        return speak(voice, text, play)
    except (PiperUnavailable, SpeakerUnavailable) as exc:
        print(exc)
        return None


def deliver(voice, text: str, play=play_audio) -> dict | None:
    """Speak the reply. Print it only when it could not be spoken."""
    timing = speak_answer(voice, text, play)
    if timing is None and text.strip():
        print(text.strip())
    return timing


def print_speech(timing: dict | None) -> None:
    if not timing:
        return
    print(f"TTS: {timing['tts_seconds']:.2f}s")
    print(f"Playback: {timing['playback_seconds']:.2f}s")
    first = timing.get("first_audio_seconds", 0.0)
    if first:
        print(f"First audio: {first:.2f}s")


def main() -> int:
    from app.config.settings import load_settings

    text = " ".join(sys.argv[1:]).strip() or "The answer is 391."
    settings = load_settings()
    voice = open_voice(settings)
    timing = deliver(voice, text)
    print_speech(timing)
    return 0 if timing else 1


if __name__ == "__main__":
    raise SystemExit(main())
