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

`app/speech/loop.py` is the voice loop. One turn records the microphone, transcribes with Faster Whisper, sends that text through the agent, and speaks the answer with Piper. Speech stays outside the graph. `python main.py` starts this loop. `python main.py --text` keeps the typed entry. MCP is not part of the loop.

The graph that exists now:

```text
START → route
          ├── fast → END
          └── reason → tool, if the model asked for one → END
                   └── multi, if 2+ independent tools were planned → END
```

Fast requests (time, date, stop, cancel, repeat, clear, exit) never call the model. Other requests make one model call. If that call asks for the calculator, the program evaluates the expression and answers. There is no second model call, because the tool result is already the reply. Recent turns sent to the model are capped at six messages.

Each turn records intent, model, and tool time, prompt size in characters and tokens, generation speed, and model load time when Ollama reports it. The first measured baseline is in `Baseline.md`.

Context is capped with `OLLAMA_NUM_CTX` (default 2048) because this model advertises a 128k window and this laptop has 8 GB of RAM. Speech-to-text sits in front of the graph, and Piper speaks the answer after it. `app/speech/loop.py` runs that sequence as one turn. MCP and persistent memory are still later.

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

## Intended tools

Web search MCP is connected. The allow-list is `web_search`. It starts only for a question that needs current information, then one model call speaks the result. Filesystem MCP is connected for Documents, Downloads, and Desktop. The allow-list is `list_directory`, `read_text_file`, and `search_files`. Write, edit, move, and delete are refused. Playwright MCP is opt-in via `PLAYWRIGHT_ENABLED=1` (Phase 10, public pages only): open-page requests resolve deterministically, then `browser_navigate` + `browser_snapshot` (trimmed, allow-listed to those two). Facts never open the browser, and signed-in browsing stays paused until the Chrome profile problem is fixed. GitHub's remote MCP server is connected in read-only mode for repos, issues, pull requests, and the signed-in user. The token stays in `.env`. Google Calendar's official remote MCP server is connected read-only plus free-busy (`list_events`, `get_event`, `list_calendars`, `search_events`, `suggest_time`); writes are refused. Sign-in is one browser OAuth flow (`python -m app.mcp.calendar_login`) with the refresh token in `data/` (gitignored). LinkedIn is not connected. Each remaining server's real tools and auth must be checked in its docs before any client code is written.

There is no separate news server. Current web information uses web search.

## Memory

Structured records live in `data/memory.json`: fact, preference, episode, and working context. The file is read only when the user asks to remember, forget, inspect, or delete. Deleting everything waits for an explicit confirmation.
