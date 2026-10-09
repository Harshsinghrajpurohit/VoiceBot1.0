"""Run a fixed set of requests and write the latency baseline."""

from datetime import date
from pathlib import Path

from app.config.settings import load_settings
from app.measure.resources import sample_gpu, sample_ram

PROMPTS = (
    ("What time is it?", "fast"),
    ("Say hello in one short sentence.", "model"),
    ("Say hello in one short sentence.", "model-warm"),
    ("What is 17 times 23?", "tool"),
)


def _cell(value) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if value is None or value == "":
        return "—"
    return str(value)


def format_report(settings, rows: list[dict], notes: list[str]) -> str:
    headers = [
        "Request",
        "Kind",
        "Intent s",
        "LLM s",
        "Tool s",
        "Load s",
        "Prompt chars",
        "Prompt tokens",
        "Output tokens",
        "Tokens/s",
        "App MB",
        "System MB",
        "GPU MB",
        "GPU %",
    ]
    lines = [
        "# Baseline",
        "",
        f"Recorded: {date.today().isoformat()}",
        f"Model: `{settings.ollama_model}`",
        f"Context window: {settings.num_ctx} tokens",
        f"Max generation: {settings.num_predict} tokens",
        "",
        "Phase 3 measurement on this laptop before speech, MCP, or memory.",
        "Targets are not set here. They come from these numbers.",
        "App MB is this program. The model runs in Ollama, so its weight shows up in system RAM and GPU memory.",
        "GPU percent is a snapshot after the reply, so a short call can finish before the sample.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [
            row["request"],
            row["kind"],
            row["intent_seconds"],
            row["llm_seconds"],
            row["tool_seconds"],
            row["load_seconds"],
            row["prompt_chars"],
            row["prompt_tokens"],
            row["output_tokens"],
            row["tokens_per_second"],
            row["process_mb"],
            row["system_used_mb"],
            row.get("gpu_memory_mb"),
            row.get("gpu_util_percent"),
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for note in notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def measure_prompts(session) -> tuple[list[dict], list[str]]:
    notes = []
    if session.llm_error:
        notes.append(session.llm_error)
        notes.append("Model rows were not run. Fast-path rows still were.")
    gpu = sample_gpu()
    if not gpu.get("gpu_available"):
        notes.append("GPU sample was unavailable. nvidia-smi did not return data.")

    rows = []
    for text, kind in PROMPTS:
        if session.llm_error and kind != "fast":
            continue
        result = session.ask(text)
        ram = sample_ram()
        gpu = sample_gpu()
        row = {
            "request": text,
            "kind": kind,
            "intent_seconds": result["intent_seconds"],
            "llm_seconds": result["llm_seconds"],
            "tool_seconds": result["tool_seconds"],
            "load_seconds": result["load_seconds"],
            "prompt_chars": result["prompt_chars"],
            "prompt_tokens": result["prompt_tokens"],
            "output_tokens": result["output_tokens"],
            "tokens_per_second": result["tokens_per_second"],
            "process_mb": ram["process_mb"],
            "system_used_mb": ram["system_used_mb"],
            "system_total_mb": ram["system_total_mb"],
        }
        if gpu.get("gpu_available"):
            row["gpu_memory_mb"] = gpu["gpu_memory_mb"]
            row["gpu_util_percent"] = gpu["gpu_util_percent"]
        rows.append(row)
        answer = result["response"].replace("\n", " ")
        notes.append(f"{kind}: {answer}")
        tool_name = result.get("tool_name") or ""
        if kind.startswith("model") and tool_name:
            notes.append(
                f"{kind} called the {tool_name} tool instead of answering in text."
            )
    if rows:
        total = rows[-1]["system_total_mb"]
        notes.append(f"System RAM: {total:.0f} MB.")
    return rows, notes


def write_baseline(path: Path, session) -> str:
    settings = session.settings
    rows, notes = measure_prompts(session)
    report = format_report(settings, rows, notes)
    path.write_text(report, encoding="utf-8")
    return report


def main() -> int:
    from main import Session

    root = Path(__file__).resolve().parents[2]
    report = write_baseline(root / "Baseline.md", Session())
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
