"""Local structured memory. Loaded only when a turn asks about memory."""

import json
import os
import re


CONFIRM = "yes delete everything you remember"
REMEMBERED = "I'll remember that."
FORGOT = "I forgot that."
UNKNOWN = "I don't have that memory."
EMPTY = "I don't remember anything about you yet."
ASK_DELETE = "Say yes, delete everything you remember, to confirm."
DELETED = "I deleted everything I remember about you."

_REMEMBER = re.compile(r"^remember(?: that)?\s+(.+)$", re.IGNORECASE)
_FORGET = re.compile(r"^forget(?: that)?\s+(.+)$", re.IGNORECASE)
_INSPECT = re.compile(
    r"^(?:what do you remember(?: about me)?|what do you know about me)$",
    re.IGNORECASE,
)
_DELETE_ALL = re.compile(
    r"^delete everything you remember(?: about me)?$",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("prefer", "i like", "i hate", "habit")):
        return "preference"
    if any(word in lowered for word in ("working on", "my goal", "current project")):
        return "context"
    if any(word in lowered for word in ("yesterday", "last week", "happened")):
        return "episode"
    return "fact"


def _clean(text: str) -> str:
    cleaned = text.strip()
    for mark in "?.!,":
        cleaned = cleaned.replace(mark, "")
    return " ".join(cleaned.split())


class MemoryStore:
    def __init__(self, path: str):
        self.path = path
        self.records: list[dict] = []
        self.pending_delete = False
        self._load()

    def respond(self, text: str) -> str | None:
        cleaned = _clean(text)
        if cleaned.lower() == CONFIRM:
            if not self.pending_delete:
                return None
            self.records = []
            self.pending_delete = False
            self._save()
            return DELETED
        if _DELETE_ALL.match(cleaned):
            self.pending_delete = True
            self._save()
            return ASK_DELETE
        if self.pending_delete:
            self.pending_delete = False
            self._save()
        remembered = _REMEMBER.match(cleaned)
        if remembered:
            return self._remember(remembered.group(1))
        forgotten = _FORGET.match(cleaned)
        if forgotten:
            return self._forget(forgotten.group(1))
        if _INSPECT.match(cleaned):
            return self._inspect()
        return None

    def _remember(self, text: str) -> str:
        note = _clean(text)
        if not note:
            return UNKNOWN
        self.records.append({"kind": classify(note), "text": note[:300]})
        self._save()
        return REMEMBERED

    def _forget(self, text: str) -> str:
        needle = _clean(text).lower()
        kept = [
            record
            for record in self.records
            if needle not in record.get("text", "").lower()
        ]
        if len(kept) == len(self.records):
            return UNKNOWN
        self.records = kept
        self._save()
        return FORGOT

    def _inspect(self) -> str:
        if not self.records:
            return EMPTY
        lines = [f"{record['kind']}: {record['text']}" for record in self.records[-5:]]
        extra = len(self.records) - len(lines)
        spoken = "I remember " + "; ".join(lines) + "."
        if extra:
            spoken += f" There are {extra} older memories."
        return spoken

    def _load(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return
        records = data.get("records") if isinstance(data, dict) else None
        if isinstance(records, list):
            self.records = [item for item in records if isinstance(item, dict)]
        self.pending_delete = bool(isinstance(data, dict) and data.get("pending_delete"))

    def _save(self) -> None:
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        payload = {"records": self.records, "pending_delete": self.pending_delete}
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
