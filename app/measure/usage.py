def prompt_chars(messages) -> int:
    total = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total += len(content)
        else:
            total += len(str(content))
    return total


def _first_int(*values) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return 0


def generation_stats(message, elapsed_seconds: float) -> dict:
    meta = getattr(message, "response_metadata", None) or {}
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(usage, dict):
        usage = {}

    prompt_tokens = _first_int(
        meta.get("prompt_eval_count"),
        usage.get("input_tokens"),
    )
    output_tokens = _first_int(
        meta.get("eval_count"),
        usage.get("output_tokens"),
    )
    eval_ns = _first_int(meta.get("eval_duration"))
    load_ns = _first_int(meta.get("load_duration"))

    if eval_ns > 0 and output_tokens > 0:
        speed = output_tokens / (eval_ns / 1_000_000_000)
    elif elapsed_seconds > 0 and output_tokens > 0:
        speed = output_tokens / elapsed_seconds
    else:
        speed = 0.0

    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "tokens_per_second": speed,
        "load_seconds": load_ns / 1_000_000_000 if load_ns else 0.0,
    }
