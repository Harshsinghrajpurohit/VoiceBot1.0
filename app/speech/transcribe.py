import time

import numpy as np


class MicrophoneUnavailable(Exception):
    """No microphone could be opened."""


class WhisperUnavailable(Exception):
    """Faster Whisper could not transcribe."""


def load_model(settings):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise WhisperUnavailable("Faster Whisper is not installed.") from exc
    try:
        return WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    except Exception as exc:
        raise WhisperUnavailable(
            f"Could not load Whisper model {settings.whisper_model}."
        ) from exc


def to_whisper_rate(audio, source_rate: int, target_rate: int = 16000):
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if source_rate == target_rate or len(samples) < 2:
        return samples
    target_len = int(len(samples) * target_rate / source_rate)
    if target_len < 2:
        return samples
    source_x = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    target_x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(target_x, source_x, samples).astype(np.float32)


def transcribe(model, audio, language: str) -> tuple[str, float]:
    started = time.perf_counter()
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(samples) == 0:
        return "", time.perf_counter() - started
    try:
        segments, _info = model.transcribe(
            samples,
            language=language or None,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 800},
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        parts = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                parts.append(text)
    except Exception as exc:
        raise WhisperUnavailable("Transcription failed.") from exc
    if not parts:
        return "", time.perf_counter() - started
    return " ".join(parts), time.perf_counter() - started
