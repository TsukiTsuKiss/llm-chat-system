"""User interrupt helpers (design.md §6.7)."""

from __future__ import annotations

from typing import Any

USER_INTERRUPT_TALENT = "user"
USER_INTERRUPT_DISPLAY = "あなた"
DEFAULT_INTERRUPT_MARKER = "【ユーザー確認】"


def normalize_interrupt_markers(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    return [str(item).strip() for item in raw if str(item).strip()]


def resolve_interrupt_markers(
    workflow: dict[str, Any] | None,
    org: dict[str, Any] | None = None,
) -> list[str]:
    """Workflow `interrupt_on` takes precedence; org has no override yet."""
    _ = org
    markers = normalize_interrupt_markers((workflow or {}).get("interrupt_on"))
    return markers


def workflow_has_interrupt_on(workflow: dict[str, Any] | None) -> bool:
    return bool(resolve_interrupt_markers(workflow))


def matched_interrupt_marker(text: str, markers: list[str]) -> str | None:
    if not text or not markers:
        return None
    for marker in markers:
        if marker in text:
            return marker
    return None
