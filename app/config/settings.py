import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    request_timeout: float
    num_ctx: int
    num_predict: int
    ollama_keep_alive: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    whisper_language: str
    record_seconds: float
    piper_voice: str
    piper_voice_dir: str
    playwright_mcp_command: str
    playwright_mcp_args: str
    playwright_enabled: bool
    filesystem_roots: str
    github_token: str
    github_mcp_url: str
    google_client_json: str
    calendar_mcp_url: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        ollama_base_url=os.getenv(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:latest"),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "60")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "2048")),
        num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "128")),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m",
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        whisper_language=os.getenv("WHISPER_LANGUAGE", "en"),
        record_seconds=float(os.getenv("WHISPER_RECORD_SECONDS", "5")),
        piper_voice=os.getenv("PIPER_VOICE", "en_US-lessac-medium"),
        piper_voice_dir=os.getenv("PIPER_VOICE_DIR", "voices"),
        playwright_mcp_command=os.getenv("PLAYWRIGHT_MCP_COMMAND", "npx"),
        playwright_mcp_args=os.getenv(
            "PLAYWRIGHT_MCP_ARGS",
            "-y @playwright/mcp@latest --extension",
        ),
        playwright_enabled=os.getenv("PLAYWRIGHT_ENABLED", "").strip().lower()
        in {"1", "true", "yes", "on"},
        filesystem_roots=os.getenv("FILESYSTEM_ROOTS", ""),
        github_token=os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
        github_mcp_url=os.getenv(
            "GITHUB_MCP_URL",
            "https://api.githubcopilot.com/mcp/",
        ),
        google_client_json=os.getenv("GOOGLE_CALENDAR_CLIENT_JSON", ""),
        calendar_mcp_url=os.getenv(
            "CALENDAR_MCP_URL",
            "https://calendarmcp.googleapis.com/mcp/v1",
        ),
    )
