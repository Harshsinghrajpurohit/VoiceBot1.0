# Phases

Build one phase at a time. Stop at the end of each phase.

Current phase: **1 — local model and graph.** Status: complete.

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

## 10 — Web and browser

Current information and site interaction through browser capability. Keep this separate from local deterministic commands.

## 11 — Voice performance

Voice activity detection, streaming, sentence-level speech, buffering, barge-in. Primary metric: time until the user hears something useful.

## 12 — Optimization

Change only what the measurements justify: prompt size, context, caching, warm-up, shorter answers, model choice.
