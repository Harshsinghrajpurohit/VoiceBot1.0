import json
import urllib.error
import urllib.request

from langchain_ollama import ChatOllama

from app.config.settings import Settings


class OllamaUnavailable(Exception):
    """Ollama did not answer."""


class ModelUnavailable(Exception):
    """The configured model is not installed."""


def list_models(base_url: str, timeout: float) -> list[str]:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OllamaUnavailable(
            "Ollama is not reachable at " + base_url
        ) from exc

    names = []
    for item in payload.get("models", []):
        name = item.get("name")
        if name:
            names.append(name)
    return names


def ensure_model(settings: Settings) -> None:
    names = list_models(settings.ollama_base_url, settings.request_timeout)
    if settings.ollama_model in names:
        return
    installed = ", ".join(names) if names else "none"
    raise ModelUnavailable(
        f"Model {settings.ollama_model} is not installed. "
        f"Installed: {installed}"
    )


def make_llm(settings: Settings) -> ChatOllama:
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        num_ctx=settings.num_ctx,
        num_predict=settings.num_predict,
        temperature=0.2,
        keep_alive=settings.ollama_keep_alive,
        sync_client_kwargs={"timeout": settings.request_timeout},
    )


def warm_up(settings: Settings) -> None:
    """Load the model into Ollama now so the first turn skips load time."""
    payload = json.dumps(
        {"model": settings.ollama_model, "keep_alive": settings.ollama_keep_alive}
    ).encode("utf-8")
    url = settings.ollama_base_url.rstrip("/") + "/api/generate"
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.request_timeout):
            pass
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OllamaUnavailable(
            "Ollama is not reachable at " + settings.ollama_base_url
        ) from exc
