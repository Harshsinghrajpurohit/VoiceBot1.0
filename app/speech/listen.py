import time

import numpy as np

from app.speech.devices import resolve_input, unmute_microphone
from app.speech.transcribe import (
    MicrophoneUnavailable,
    to_whisper_rate,
    transcribe,
)

WHISPER_RATE = 16000
CHUNK_SECONDS = 0.1
CALIBRATE_SECONDS = 0.3
MIN_SECONDS = 0.8
MAX_SECONDS = 8.0
MIN_SPEECH_SECONDS = 0.4
SILENCE_RMS = 0.008
SILENCE_SECONDS = 0.8
MIN_LEVEL = 0.001


def _loudness(audio) -> float:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def downmix(audio):
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 2 and samples.shape[1] > 1:
        return samples.mean(axis=1).astype(np.float32)
    return samples.reshape(-1)


def _preferred_input(mics):
    return mics


def calibrate_threshold(stream, sample_rate: int, width: int) -> float:
    """Measure room noise right before speech. Floor the result."""
    frames = max(1, int(CALIBRATE_SECONDS * sample_rate))
    got = 0
    total = 0.0
    while got < frames:
        chunk, _overflow = stream.read(min(width, frames - got))
        mono = downmix(np.asarray(chunk, dtype=np.float32))
        total += float(np.sum(mono * mono))
        got += len(mono)
    noise = (total / max(got, 1)) ** 0.5
    return max(noise * 3.0, MIN_LEVEL)


def trim_edges(audio, sample_rate: int, threshold: float) -> object:
    """Drop leading/trailing silence so Whisper only hears speech."""
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(samples) == 0:
        return samples
    width = max(1, int(sample_rate * CHUNK_SECONDS))
    first = 0
    for start in range(0, len(samples), width):
        if _loudness(samples[start : start + width]) >= threshold:
            first = start
            break
    else:
        return np.zeros(1, dtype=np.float32)
    last = len(samples)
    for start in range(len(samples) - width, -1, -width):
        if _loudness(samples[start : start + width]) >= threshold:
            last = min(len(samples), start + width)
            break
    return samples[first:last]


def voice_active(audio, threshold: float = SILENCE_RMS) -> bool:
    """True when a chunk holds speech instead of room silence."""
    return _loudness(audio) >= threshold


def trailing_silence(audio, sample_rate: int, threshold: float = SILENCE_RMS) -> float:
    """Seconds of quiet at the end of one recording."""
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(samples) == 0:
        return 0.0
    width = max(1, int(sample_rate * CHUNK_SECONDS))
    quiet = 0
    for start in range(len(samples) - width, -1, -width):
        if _loudness(samples[start : start + width]) >= threshold:
            break
        quiet += 1
    else:
        if len(samples) % width:
            if _loudness(samples[: len(samples) % width]) >= threshold:
                return quiet * CHUNK_SECONDS
            quiet += len(samples) % width / width
    return quiet * CHUNK_SECONDS


def record_audio(seconds: float, sample_rate: int | None = None):
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise MicrophoneUnavailable("Audio capture is not installed.") from exc

    if unmute_microphone():
        print("The microphone was muted. It is on now.")

    started = time.perf_counter()
    try:
        mics = _preferred_input(resolve_input(sd))
        width = max(1, int(CHUNK_SECONDS * 44100))
        streams = []
        try:
            for device_index, _name in mics:
                info = sd.query_devices(device_index)
                rate = int(info["default_samplerate"])
                channels = min(2, int(info["max_input_channels"]))
                width = max(1, int(rate * CHUNK_SECONDS))
                stream = sd.InputStream(
                    samplerate=rate,
                    channels=channels,
                    dtype="float32",
                    device=device_index,
                )
                stream.start()
                streams.append((stream, rate))
            if not streams:
                raise MicrophoneUnavailable("The microphone is not available.")
            threshold = calibrate_threshold(streams[0][0], streams[0][1], width)
            pieces = []
            quiet = 0.0
            speech = 0.0
            while True:
                heard_all = []
                for stream, rate in streams:
                    chunk, _overflow = stream.read(width)
                    heard_all.append(
                        to_whisper_rate(
                            downmix(np.asarray(chunk, dtype=np.float32)),
                            rate,
                            WHISPER_RATE,
                        )
                    )
                mono = max(heard_all, key=_loudness)
                pieces.append(mono)
                heard = (
                    np.concatenate(pieces)
                    if len(pieces) > 1
                    else np.asarray(pieces[0], dtype=np.float32)
                )
                heard_seconds = len(heard) / WHISPER_RATE
                if _loudness(mono) >= threshold:
                    quiet = 0.0
                    speech += CHUNK_SECONDS
                else:
                    quiet += CHUNK_SECONDS
                if heard_seconds < MIN_SECONDS:
                    if heard_seconds >= MAX_SECONDS:
                        break
                    continue
                if (
                    speech >= MIN_SPEECH_SECONDS
                    and quiet >= SILENCE_SECONDS
                ):
                    break
                if heard_seconds >= MAX_SECONDS:
                    break
            heard = (
                np.concatenate(pieces)
                if pieces
                else np.zeros(1, dtype=np.float32)
            )
        finally:
            for stream, _rate in streams:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
    except MicrophoneUnavailable:
        raise
    except Exception as exc:
        raise MicrophoneUnavailable("The microphone is not available.") from exc

    trimmed = trim_edges(heard, WHISPER_RATE, threshold)
    speech_seconds = len(trimmed) / WHISPER_RATE
    if _loudness(heard) < MIN_LEVEL or speech_seconds < MIN_SPEECH_SECONDS:
        print("I didn't catch that. Please speak again.")
        return np.zeros(1, dtype=np.float32), time.perf_counter() - started
    return trimmed, time.perf_counter() - started


def forward_heard(session, heard: dict) -> dict | None:
    """Send recognized speech into the text agent. Silence is not a request."""
    text = (heard.get("text") or "").strip()
    if not text:
        return None
    return session.ask(text)


def listen_once(settings, model, record=record_audio) -> dict:
    audio, capture_seconds = record(settings.record_seconds)
    text, stt_seconds = transcribe(model, audio, settings.whisper_language)
    return {
        "text": text,
        "capture_seconds": capture_seconds,
        "stt_seconds": stt_seconds,
    }
