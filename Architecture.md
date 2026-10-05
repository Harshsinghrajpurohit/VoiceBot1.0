# Architecture

Local-first and latency-aware. The language model is the expensive step. Most of the design exists to avoid calling it, and to keep each call small.

## Runtime

| Piece | Choice |
| --- | --- |
| Orchestration | LangGraph |
| Model | Ollama, `llama3.2:latest` |
| Speech-to-text | Faster Whisper, local |
| Text-to-speech | Piper, local |
| Audio I/O | sounddevice |
| Tools | MCP client, added one server at a time |
| Memory | Structured local storage, not a vector database |

Model name, Ollama URL, Whisper model, Piper voice, timeouts, and log level live in environment settings. They are not hard-coded in modules.

## Request flow

```text
Microphone
    ↓
Faster Whisper
    ↓
Intent check
    ├── simple → direct function → text
    └── otherwise → LangGraph
                        ↓
                   small prompt
                        ↓
                   Ollama, only if needed
                        ↓
              memory / MCP / browser, only if needed
                        ↓
                   short text answer
    ↓
Piper
    ↓
Speaker
```

The graph stays small:

```text
START → input → fast-path check
                  ├── fast path → response
                  └── agent path → reason → tools if required → response
response → END
```

Speech is outside the graph until the voice loop exists.

Phase 1 is the slice that exists now: text in, one `generate` node, Ollama, text out. The fast-path check is not in the graph yet. `exit` in the CLI only leaves the program. Context is capped with `OLLAMA_NUM_CTX` (default 2048) because this model advertises a 128k window and this laptop has 8 GB of RAM.

## Latency rules

- Measure each stage. Do not guess the bottleneck.
- Log STT, intent, LLM, tool, memory, TTS, time to first audio, and total time.
- Skip memory lookup when the request does not need memory.
- Do not send the full chat, every tool description, or every memory into the model.
- Prefer one planning call, then tool execution, then one answer call.
- Run independent tools together. Do not parallelize steps that depend on each other.
- Spoken answers stay short: answer, important detail, optional follow-up.

Streaming (first sentence to Piper while the model continues) is a later phase. The metric that matters then is time to first audio.

## Tool safety

The model chooses a tool. The application validates the call and runs it. There is no `eval` of model output.

Read-only tools can run directly. Destructive tools (delete, send, modify, publish, create an event) ask for confirmation first.

If Ollama is down, deterministic commands still work. If a tool is down, say which one failed. If Piper fails, print the text. If Whisper fails, say so and allow another attempt.

## Intended tools (not built yet)

Playwright, Google Calendar, filesystem, GitHub, LinkedIn. Each server's real tools and auth must be checked in its docs before any client code is written.

Current web information uses browser capability. There is no separate news server.

## Not built yet

No voice loop, no MCP client, no memory store. Those start in later phases, one phase at a time.
