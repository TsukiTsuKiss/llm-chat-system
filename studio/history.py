"""Role conversation history (Chat.py 移植)."""

from __future__ import annotations

from langchain_core.messages import BaseMessage


class ConversationHistory:
    def __init__(self, max_length: int = 10) -> None:
        self.max_length = max_length
        self.messages: list[BaseMessage] = []

    def add_message(self, message: BaseMessage) -> None:
        self.messages.append(message)
        if len(self.messages) > self.max_length * 2:
            self.messages = self.messages[-self.max_length * 2 :]

    def get_messages(self) -> list[BaseMessage]:
        return self.messages

    def reduce_history(self, reduction_factor: float = 0.5) -> bool:
        if len(self.messages) > 2:
            new_length = max(2, int(len(self.messages) * reduction_factor))
            self.messages = self.messages[-new_length:]
            return True
        return False

    def get_history_size_estimate(self) -> int:
        total = 0
        for message in self.messages:
            if hasattr(message, "content"):
                total += len(str(message.content))
        return total


class RoleHistories:
    def __init__(self, max_length: int = 10) -> None:
        self._histories: dict[str, ConversationHistory] = {}
        self.max_length = max_length

    def for_talent(self, talent_id: str) -> ConversationHistory:
        if talent_id not in self._histories:
            self._histories[talent_id] = ConversationHistory(self.max_length)
        return self._histories[talent_id]

    def reduce_for_talent(self, talent_id: str) -> bool:
        return self.for_talent(talent_id).reduce_history()
