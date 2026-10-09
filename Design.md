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
| Speech to text | Faster Whisper | `small`, CPU, int8. The chat model already uses about 2.6 GB of the 4 GB GPU. |
| Text to speech | Piper | `en_US-lessac-medium` on CPU. One voice. Short utterances. |

Audio capture and playback use sounddevice. Listening uses the laptop microphone array, and also a headset microphone when one is present. The louder input is the one that is transcribed. Playback follows what is connected: an active headphone, headset, or earphone device receives the answer. When none is connected, the answer plays through the laptop speakers. The program does not ask which one is being worn. Phase 11 records in 0.1 s chunks with a per-turn calibrated energy voice detector (0.3 s room sample, threshold noise x3 floored at 0.001, all mics recorded with the loudest kept) and stops after 0.8 s of trailing silence once 0.4 s of speech is heard (minimum 0.8 s, maximum 8 s), then trims silence edges and transcribes with Faster Whisper (`vad_filter=True`, `min_silence_duration_ms=800`, no previous-text conditioning, `no_speech_threshold=0.6`). Empty or too-short captures ask for a repeat instead of reaching the model. Language is set to English so the model does not spend time detecting it. Beam size is 1. `WHISPER_RECORD_SECONDS` is now the upper bound, not a fixed wait. Replies are spoken sentence by sentence so the first sentence is heard quickly; every turn logs `first_audio_seconds`. Barge-in is not done. The model name, device, and compute type come from settings.

Phase 6 runs one repeating turn in `app/speech/loop.py`: microphone, Faster Whisper, the existing agent, Piper, then the speaker or headphones. A microphone, Whisper, model, or speaker failure is reported and the loop waits for another turn. MCP is not included.

A successful reply is spoken and is not printed. If Piper fails, print the answer. If Whisper fails, report the error and accept another attempt.

## When to call the model

| Request | Path |
| --- | --- |
| Time, date, stop, exit, cancel, repeat, clear | Direct function |
| Needs reasoning, tools, memory, or the web | LangGraph + Ollama |

Fast-path matching should be narrow. If the match is uncertain, use the agent path.

The only local tool in Phase 2 is a calculator. It is offered only when the request contains a number and an arithmetic operation. A fact question, such as a capital city, is answered by the model and does not call the calculator. A valid calculator result is spoken as the answer. If the model sends a non-arithmetic expression, that rejection is not spoken; the model answers the question instead. Unknown tool names are refused.

## Prompts and answers

System prompt, history, memories, and tool text stay short. Send only the recent turns required to answer. Summarize only when the history itself becomes the cost.

Spoken answers are short. Long text costs generation time and Piper time.

## Memory (Phase 8)

Four kinds, stored as structured records:

- Personal facts (name, education, work, projects)
- Preferences (style, habits, frequent tools)
- Episodic notes (important past events)
- Working context (current goal or project)

Commands: "Remember that…", "Forget that…", "What do you remember about me?", "Delete everything you remember about me."

Those commands are answered directly. Deletion of everything asks for the exact confirmation "yes, delete everything you remember" and does nothing until that is said. The store is a local JSON file, `data/memory.json`, and it is not sent to the model on other turns.

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

Phase 7 connects one server at a time. Web search is a local MCP (`python -m app.mcp.search_server`). It has no API key. It reads DuckDuckGo results and allows only `web_search`. A question uses it when it asks for current information, such as weather, news, or “search for …”. That choice does not call the model. After the results come back, one short model call turns them into the spoken answer. A fact the local model can answer, such as a capital city, does not search.

Filesystem uses the official server `@modelcontextprotocol/server-filesystem`. It has no API key. The voice loop may only `list_directory`, `read_text_file`, and `search_files`, and only inside Documents, Downloads, and Desktop unless `FILESYSTEM_ROOTS` names other folders. Writing, editing, moving, and deleting are refused. A file question does not call the model until the listing or file text is back, and then one short model call speaks it.

GitHub uses the official remote server at `https://api.githubcopilot.com/mcp/`. There is no local GitHub process and no Docker. This client does not run a browser OAuth flow. It sends `GITHUB_PERSONAL_ACCESS_TOKEN` from `.env` as a bearer token. The request asks only for the read-only repos, issues, pull requests, and users toolsets. Creating, merging, and deleting are refused.

Google Calendar uses the official remote server at `https://calendarmcp.googleapis.com/mcp/v1`. There is no local Calendar process and no Docker. The allow-list is `list_events`, `get_event`, `list_calendars`, `search_events`, plus `suggest_time` for free-busy. Creating, updating, deleting, and responding are refused. Auth is Desktop OAuth with PKCE and a loopback redirect: set `GOOGLE_CALENDAR_CLIENT_JSON` to the Desktop-app client JSON, run `python -m app.mcp.calendar_login` once for a browser sign-in, and the refresh token is saved to `data/google_token.json` (gitignored). Each call refreshes a short-lived access token; a revoked token speaks the sign-in message again. Date ranges (today, tomorrow, this week) are computed deterministically in local time with no UTC offset, per the tool schema — the model never computes dates.

Playwright is opt-in (Phase 10). Off by default; set `PLAYWRIGHT_ENABLED=1`
to wire `PlaywrightBrowser` into the session for public pages only. Open-page
requests resolve deterministically (`resolve_page`), open with
`browser_navigate`, and read with `browser_snapshot`, trimmed to 1200 chars;
facts never open the browser. Signed-in browsing stays paused — the window it
opened had no saved sign-in. Fix that with the Playwright extension, or Chrome
remote debugging, before using it for signed-in sites. Google Calendar and
LinkedIn are still later.

Independent tools may run together. A tool that needs another tool's result waits.

## Latency log

Development log only. Not spoken to the user.

```text
Request ID
STT, Intent, LLM, Tool, Memory, TTS
TTFT, TTFA, Total
```

Phase 3 records the first baseline in `Baseline.md`. Targets are set after that measurement, not before. The CLI prints intent, model, tool, prompt size, and generation speed on every turn. RAM and GPU are sampled by the baseline run, not on every reply.

## Errors that must not kill the process

Ollama down, model missing, Whisper failure, Piper failure, MCP down or unauthenticated, web or network failure, bad tool call, timeout, microphone missing, speaker missing, machine out of memory.

Fallback: deterministic commands still run; name the capability that failed; show text if speech output fails.
