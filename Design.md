# Design

Decisions that later code should follow. Phase 0 does not implement them.

## Model

Use the Ollama model already on this machine: `llama3.2:latest`.

It is about 2 GB, which matches a small 3B-class quant. The tag `llama3.2:3b` is not installed. Do not pull it unless asked. If a different model is wanted later, change `OLLAMA_MODEL`. No module should embed the model name.

Ollama URL default: `http://127.0.0.1:11434`.

`llama3.2:latest` reports a 131072-token window. Phase 1 sets `OLLAMA_NUM_CTX` to 2048 and `OLLAMA_NUM_PREDICT` to 128. A larger window would spend RAM and time on context this laptop does not need for a short reply.

## Speech

Both sides stay on this machine. No cloud speech APIs.

| Direction | Engine | Notes |
| --- | --- | --- |
| Speech to text | Faster Whisper | Small model first. This GPU has 4 GB. |
| Text to speech | Piper | One local voice. Short utterances. |

Audio capture and playback use sounddevice. Early phases may record a fixed window. Voice activity detection and barge-in wait until the basic loop works (Phase 11).

If Piper fails, print the answer. If Whisper fails, report the error and accept another attempt.

## When to call the model

| Request | Path |
| --- | --- |
| Time, date, stop, exit, cancel, repeat, clear | Direct function |
| Needs reasoning, tools, memory, or the web | LangGraph + Ollama |

Fast-path matching should be narrow. If the match is uncertain, use the agent path.

## Prompts and answers

System prompt, history, memories, and tool text stay short. Send only the recent turns required to answer. Summarize only when the history itself becomes the cost.

Spoken answers are short. Long text costs generation time and Piper time.

## Memory (Phase 8)

Four kinds, stored as structured records:

- Personal facts (name, education, work, projects)
- Preferences (style, habits, frequent tools)
- Episodic notes (important past events)
- Working context (current goal or project)

Commands to support later: "Remember that…", "Forget that…", "What do you remember about me?", "Delete everything you remember about me."

Deletion of everything requires an explicit confirmation. Do not load the whole store into the model on every turn.

No Chroma, FAISS, Pinecone, or embedding model unless a later request adds retrieval.

## Tools (Phase 7 and later)

Planned servers, each unverified until its docs are read:

1. Playwright — sites that need real browser interaction
2. Google Calendar
3. Filesystem
4. GitHub
5. LinkedIn

Read-only calls run after validation. Destructive calls ask first.

The model returns a tool name and arguments. Application code checks the name against an allow-list and runs it. No arbitrary Python.

Independent tools may run together. A tool that needs another tool's result waits.

## Latency log

Development log only. Not spoken to the user.

```text
Request ID
STT, Intent, LLM, Tool, Memory, TTS
TTFT, TTFA, Total
```

Phase 3 records the first baseline. Targets are set after that measurement, not before.

## Errors that must not kill the process

Ollama down, model missing, Whisper failure, Piper failure, MCP down or unauthenticated, web or network failure, bad tool call, timeout, microphone missing, speaker missing, machine out of memory.

Fallback: deterministic commands still run; name the capability that failed; show text if speech output fails.
