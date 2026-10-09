from datetime import datetime


def current_time() -> str:
    now = datetime.now()
    clock = now.strftime("%I:%M %p").lstrip("0")
    return "It's " + clock + "."


def current_date() -> str:
    now = datetime.now()
    month = now.strftime("%B")
    weekday = now.strftime("%A")
    return f"Today is {weekday}, {month} {now.day}, {now.year}."
