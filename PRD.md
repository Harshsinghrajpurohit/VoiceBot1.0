# Product Requirements

Personal, local, self-use voice agent. It runs on this machine. It is not a cloud chatbot.

## Goal

Speak a request and hear a short spoken answer. The system listens, understands the request, does only the work that request needs, and speaks back.

```text
Voice → STT → Intent → Fast path or Agent path → Response → TTS → Voice
```

Speech stays on the machine:

- Speech-to-text: Faster Whisper
- Text-to-speech: Piper

No cloud speech APIs.

## Hardware

- ASUS TUF Gaming F17
- RTX 2050, 4 GB VRAM
- 8 GB RAM
- Intel i5-11400H
- Windows 11

Local inference is slower than a cloud model. Latency is a design constraint, not a later polish step.

## What the agent must do

1. Listen, then transcribe with Faster Whisper.
2. Decide whether a language model is needed.
3. Handle simple requests with a direct function.
4. Use a local model only when reasoning is required.
5. Call tools, including MCP tools, only when the request needs them.
6. Use the browser for current information when the request needs it.
7. Remember useful facts about the user across sessions.
8. Speak a concise answer with Piper.

## Fast path

Deterministic requests skip the model.

Examples: current time, today's date, stop, exit, cancel, repeat, clear conversation.

## Agent path

Requests that need reasoning, tools, memory, or the web go through LangGraph and the local model.

Example: check tomorrow's calendar and say whether anything important is scheduled.

## Language model

Ollama, model name from configuration.

Initial model: `llama3.2:latest` (already installed, about 2 GB). Do not pull another model unless asked.

## Out of scope

- Retrieval-augmented generation and vector databases
- Cloud speech or a cloud-first language model
- Arbitrary code execution from the model
- A graphical interface
- Background autonomous agents

## Done when

A spoken request can be answered by voice, simple requests avoid the model, complex requests can use tools and memory, secrets stay out of the repo, and each stage reports its latency.
