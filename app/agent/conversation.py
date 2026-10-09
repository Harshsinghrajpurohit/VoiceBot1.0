class Conversation:
    """Recent turns for the model. Not persistent memory."""

    def __init__(self, limit: int = 6):
        self.limit = limit
        self.turns = []
        self.last_response = ""

    def add(self, user_text: str, answer: str) -> None:
        self.last_response = answer
        self.turns.append(("user", user_text))
        self.turns.append(("assistant", answer))
        self.turns = self.turns[-self.limit :]

    def clear(self) -> None:
        self.turns = []
        self.last_response = ""
