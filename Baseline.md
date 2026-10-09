# Baseline

Recorded: 2026-10-05
Model: `llama3.2:latest`
Context window: 2048 tokens
Max generation: 128 tokens

Phase 3 measurement on this laptop before speech, MCP, or memory.
Targets are not set here. They come from these numbers.
App MB is this program. The model runs in Ollama, so its weight shows up in system RAM and GPU memory.
GPU percent is a snapshot after the reply, so a short call can finish before the sample.

| Request | Kind | Intent s | LLM s | Tool s | Load s | Prompt chars | Prompt tokens | Output tokens | Tokens/s | App MB | System MB | GPU MB | GPU % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| What time is it? | fast | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | 0 | 0.00 | 79.50 | 7315.10 | 2667.00 | 0.00 |
| Say hello in one short sentence. | model | 0.00 | 0.36 | 0.00 | 0.00 | 203 | 212 | 12 | 50.23 | 79.80 | 7197.40 | 2669.00 | 0.00 |
| Say hello in one short sentence. | model-warm | 0.00 | 0.36 | 0.00 | 0.00 | 267 | 235 | 13 | 51.69 | 79.90 | 7169.30 | 2669.00 | 56.00 |
| What is 17 times 23? | tool | 0.00 | 0.43 | 0.00 | 0.01 | 319 | 259 | 17 | 50.49 | 80.10 | 7166.90 | 2669.00 | 96.00 |

## Notes

- fast: It's 4:40 PM.
- model: That calculation is not allowed.
- model called the calculator tool instead of answering in text.
- model-warm: That calculation is not allowed.
- model-warm called the calculator tool instead of answering in text.
- tool: {"name":"calculator",""parameters":{"expression":"17 * 23"}}
- System RAM: 7915 MB.

## Speech-to-text

Recorded: 2026-10-05
Model: Faster Whisper `small`, CPU, int8
Window: 5 seconds from the microphone, resampled to 16 kHz

| Stage | Time |
| --- | --- |
| First load, including the model download | 107.46 s |
| Later load from the local cache | 4.33 s |
| Capture | 5.62 s |
| Transcription | 2.11 s |

The transcript was empty. The window was room audio, so this measures a short recording with little speech. A spoken sentence can take longer because Whisper has more text to emit. Voice activity detection is not on yet, so the program always waits for the full window.

## Text-to-speech

Recorded: 2026-10-05
Voice: Piper `en_US-lessac-medium`, CPU
Sentence: "The answer is 391."

| Stage | Time |
| --- | --- |
| First load, including the voice download | 17.07 s |
| Later load from `voices/` | 2.32 s |
| Synthesis | 0.18 s |
| Playback | 2.18 s |

Playback is how long the spoken sentence lasts. Synthesis is the time Piper takes to create the audio. A second short sentence, "It is four thirty.", took 0.08 s to synthesize and 1.20 s to play.

## Voice loop

Recorded: 2026-10-05
Path: microphone, Faster Whisper, agent, Piper, speaker or headphones. No MCP.

| Stage | Time | Source |
| --- | --- | --- |
| Capture | 5.62 s | Phase 4, 5-second window |
| Transcription | 2.11 s | Phase 4, room audio |
| Agent, "What is the capital of Japan?" | 0.23 s | This run |
| Synthesis | 0.14 s | This run |
| Playback | 2.37 s | This run, headphones |
| Loop, these stages added | 10.47 s | |

The capture window is still fixed, so most of the wait happens before the model starts. The spoken answer in this run was "The capital of Japan is Tokyo."

## Voice performance (Phase 11)

Recorded: 2026-10-08
Voice: Piper `en_US-lessac-medium`, CPU
Reply: "It is four thirty. The answer is three hundred ninety one."

| Stage | Time |
| --- | --- |
| Whole-reply synthesis | 1.14 s |
| First-sentence synthesis (time to first audio) | 0.29 s |

Capture now stops on 0.7 s of trailing silence (min 0.8 s, max 8 s) instead of always waiting the full `WHISPER_RECORD_SECONDS` window, and `speak()` synthesizes sentence by sentence so the first sentence plays while later ones render. `first_audio_seconds` is logged on every turn. Barge-in is not done: playback still runs to completion.

## Optimization (Phase 12)

Recorded: 2026-10-08
Model: `llama3.2:latest`, `OLLAMA_KEEP_ALIVE=30m`, warm-up at session startup.

| Turn | LLM s | Load s |
| --- | --- | --- |
| 1st (cold, per-process load) | 9.11 | 8.81 |
| 2nd (warm) | 0.32 | 0.03 |
| 3rd, calculator (warm) | 0.60 | 0.03 |

Only change justified: keep-alive + warm-up moves the ~9 s load from the first voice turn to startup. `num_ctx=2048`, `num_predict=128`, prompt/history caps, and model choice unchanged — warm turns already sub-second. Cross-process runs still pay one load (Ollama evicts under 8 GB RAM / 4 GB VRAM); within a session every turn after the first stays warm.
