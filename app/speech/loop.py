"""One voice turn: microphone, Whisper, the agent, then Piper."""

import time

from app.config.settings import load_settings
from app.speech.devices import resolve_input, resolve_output
from app.speech.listen import listen_once
from app.speech.speak import deliver, open_voice, print_speech
from app.speech.transcribe import (
    MicrophoneUnavailable,
    WhisperUnavailable,
    load_model,
)


def voice_turn(
    settings,
    whisper_model,
    voice,
    session,
    listen=listen_once,
    speak=deliver,
) -> dict:
    """Run one turn. A speech failure is returned, not raised."""
    try:
        heard = listen(settings, whisper_model)
    except (MicrophoneUnavailable, WhisperUnavailable) as exc:
        return {"ok": False, "error": str(exc), "should_exit": False}

    text = (heard.get("text") or "").strip()
    turn = {
        "ok": True,
        "error": "",
        "heard": text,
        "capture_seconds": heard.get("capture_seconds", 0.0),
        "stt_seconds": heard.get("stt_seconds", 0.0),
        "answer": None,
        "speech": None,
        "should_exit": False,
    }
    if not text:
        return turn
    try:
        answer = session.ask(text)
    except Exception as exc:
        turn["ok"] = False
        turn["error"] = str(exc)
        return turn
    turn["answer"] = answer
    turn["should_exit"] = bool(answer.get("should_exit"))
    turn["speech"] = speak(voice, answer.get("response", ""))
    return turn


def print_turn(turn: dict) -> None:
    from main import print_answer

    if turn.get("error"):
        print(turn["error"])
        print("Try again.")
        return
    print(f"Heard: {turn.get('heard') or '(nothing recognized)'}")
    print(f"Capture: {turn.get('capture_seconds', 0.0):.2f}s")
    print(f"STT: {turn.get('stt_seconds', 0.0):.2f}s")
    answer = turn.get("answer")
    if not answer:
        return
    print_speech(turn.get("speech"))
    print_answer(answer)
    speech = turn.get("speech") or {}
    total = (
        turn.get("capture_seconds", 0.0)
        + turn.get("stt_seconds", 0.0)
        + answer["intent_seconds"]
        + answer["llm_seconds"]
        + answer["tool_seconds"]
        + speech.get("tts_seconds", 0.0)
        + speech.get("playback_seconds", 0.0)
    )
    print(f"Loop: {total:.2f}s")


def run() -> int:
    settings = load_settings()
    print(
        f"Loading Whisper {settings.whisper_model} "
        f"on {settings.whisper_device} ({settings.whisper_compute_type})."
    )
    started = time.perf_counter()
    try:
        whisper_model = load_model(settings)
    except WhisperUnavailable as exc:
        print(exc)
        return 1
    print(f"Model load: {time.perf_counter() - started:.2f}s")
    voice = open_voice(settings)

    from main import Session

    session = Session()
    if session.llm_error:
        print(session.llm_error)
        print("Simple commands still work.")
    try:
        import sounddevice as sd

        mics = ", ".join(name for _index, name in resolve_input(sd))
        _speaker, speaker_name = resolve_output(sd)
        print(f"Listening: {mics}")
        print(f"Speaking now: {speaker_name}")
    except Exception as exc:
        print(f"Audio devices could not be listed: {exc}")
    print(
        "Press Enter and speak. Recording stops after a short silence. "
        "Type exit to quit."
    )
    while True:
        try:
            command = input("You: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if command in {"exit", "quit"}:
            return 0
        turn = voice_turn(settings, whisper_model, voice, session)
        print_turn(turn)
        if turn.get("should_exit"):
            return 0
