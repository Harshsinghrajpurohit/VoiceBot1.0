# Phases

Build one phase at a time. Stop at the end of each phase.

Current phase: **12 — Optimization.** Status: complete.

Phase 7 remains available: web search, filesystem, remote GitHub, and Google Calendar are connected. Playwright is paused.

Playwright sign-in is deferred. The browser it opened was a separate window, so the user was not signed in. Using the existing Chrome profile needs the Playwright extension, or remote debugging enabled in Chrome. Do not start Playwright from the voice loop until that is fixed.

## 0 — Foundation

Write the product, architecture, rules, phases, and design docs, plus `.gitignore` and `.env.example`.

Done when those files exist and describe the local-first design. No voice, MCP, or memory code.

## 1 — Local model and graph

Text in, LangGraph, Ollama (`llama3.2:latest`), text out.

Done when a text request returns a model reply, the model name comes from config, a basic test passes, and a failure (Ollama down or model missing) is reported instead of crashing.

## 2 — Basic agent

Intent check, fast path, tool decision, a few local tools, one agent loop.

Done when a simple request skips the model and a tool request uses the model only as needed.

## 3 — Latency baseline

Measure model latency, tool latency, prompt size, generation speed, RAM, and GPU use. Record the baseline before adding more capability.

## 4 — Speech-to-text

Microphone, audio, Faster Whisper, text. Local only. Record STT latency. Start with a small Whisper model that fits this laptop.

## 5 — Text-to-speech

Text, Piper, audio, speaker. Local only. Record TTS latency.

## 6 — Voice loop

Microphone → Faster Whisper → agent → Piper → speaker. Leave MCP out until this loop is stable.

## 7 — MCP

MCP client, then one verified server at a time. Check official tool lists and auth before writing a client. Do not add every server in one step.

## 8 — Memory

Structured persistent memory: remember, retrieve, forget, inspect, delete. Retrieve only when the request needs memory.

## 9 — Multi-tool

Several tools in one request. One planning model call when possible. Parallel execution only for independent tools.

Done: `reason` splits on `and then`/`and`/`;` and plans one call per part from different sources (GitHub, filesystem, web search, browser). Two or more independent calls run together in `run_multi` (`ThreadPoolExecutor`, max 4), then one short model call speaks the combined answer. Single-tool requests keep their old path (model chooses calculator/browser). Dependent tools wait — this phase only runs independent calls.

## 10 — Web and browser

Current information and site interaction through browser capability. Keep this separate from local deterministic commands.

Done: web search stays the default for current information; the browser is opt-in (`PLAYWRIGHT_ENABLED=1`) and the session wires `PlaywrightBrowser` only then. Open-page requests use `resolve_page` deterministically and read via `browser_navigate` + `browser_snapshot`, trimmed to 1200 chars with an allow-list of those two tools. Facts never open the browser; without the flag the old model path is unchanged. Signed-in browsing stays paused until the Chrome profile problem is fixed. `tests/test_phase10.py` locks the separation.

## 11 — Voice performance

Voice activity detection, streaming, sentence-level speech, buffering, barge-in. Primary metric: time until the user hears something useful.

Done: capture uses per-turn room calibration (0.3 s) with a noise-adaptive energy threshold (noise x3, floor 0.001), records all mics and keeps the loudest, stops after 0.8 s trailing silence only once 0.4 s of speech is heard (min 0.8 s, max 8 s), trims leading/trailing silence, and asks you to repeat when nothing usable was caught. Whisper runs with `vad_filter=True`, `min_silence_duration_ms=800`, `condition_on_previous_text=False`, `no_speech_threshold=0.6`, and empty output is silence, not a request. Replies are spoken sentence-first with `first_audio_seconds` logged per turn. Measured on Piper `en_US-lessac-medium`: two-sentence reply whole-synth ~1.1 s vs first-sentence ~0.3 s. Barge-in (stop playback on new speech) is not done — playback still runs to completion.

## 12 — Optimization

Change only what the measurements justify: prompt size, context, caching, warm-up, shorter answers, model choice.

Done: measured first — cold first turn ~9 s (load ~8.8 s), warm turns 0.3–0.6 s. The only justified change: `OLLAMA_KEEP_ALIVE=30m` (new setting, passed to `ChatOllama`) plus a `warm_up()` call at session startup so the load happens before the first voice turn, not during it. `num_ctx=2048`, `num_predict=128`, prompt/history caps, and model choice are unchanged — warm-turn latency is already sub-second, so no other change was justified. New cross-process runs still pay one load (Ollama-side eviction under 8 GB RAM / 4 GB VRAM); within a session all turns after the first stay warm. `tests/test_phase1.py` locks the setting and warm-up call.
