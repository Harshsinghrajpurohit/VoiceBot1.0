def normalize(text: str) -> str:
    cleaned = text.strip().lower().replace("'", "")
    for mark in "?.!":
        cleaned = cleaned.replace(mark, "")
    return " ".join(cleaned.split())


FAST_INTENTS = {
    "what time is it": "time",
    "whats the time": "time",
    "what is the time": "time",
    "tell me the time": "time",
    "current time": "time",
    "whats todays date": "date",
    "what is todays date": "date",
    "whats the date": "date",
    "what is the date": "date",
    "what is the date today": "date",
    "todays date": "date",
    "what day is it": "date",
    "stop": "stop",
    "cancel": "cancel",
    "repeat": "repeat",
    "repeat that": "repeat",
    "say that again": "repeat",
    "clear conversation": "clear",
    "clear the conversation": "clear",
    "reset conversation": "clear",
    "exit": "exit",
    "quit": "exit",
}


def detect_intent(text: str) -> str:
    return FAST_INTENTS.get(normalize(text), "")
