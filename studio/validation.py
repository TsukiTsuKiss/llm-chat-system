"""Studio validation errors (design.md 5.3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioError:
    code: str
    target: str
    message: str
    hint: str = ""

    def format(self) -> str:
        if self.hint:
            return f"[{self.code}] {self.target}: {self.message}（{self.hint}）"
        return f"[{self.code}] {self.target}: {self.message}"


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[StudioError] = []

    def add(self, error: StudioError) -> None:
        self.errors.append(error)

    def extend(self, errors: list[StudioError]) -> None:
        self.errors.extend(errors)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_failed(self) -> None:
        if self.errors:
            raise StudioValidationError(self.errors)


class StudioValidationError(Exception):
    def __init__(self, errors: list[StudioError]) -> None:
        self.errors = errors
        lines = [e.format() for e in errors]
        super().__init__("\n".join(lines))

    def format_all(self) -> str:
        return "\n".join(e.format() for e in self.errors)
