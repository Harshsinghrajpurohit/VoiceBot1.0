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
    )
