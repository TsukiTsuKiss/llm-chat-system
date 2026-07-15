"""User context loading and session enablement (design.md Appendix D)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_USER_CONTEXT_PATH = "user_context/my_context.md"
DEFAULT_MAX_CHARS = 8000


def user_context_max_chars(studio_config: dict[str, Any]) -> int:
    uc = studio_config.get("user_context") or {}
    raw = uc.get("max_chars", DEFAULT_MAX_CHARS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_CHARS
    if value <= 0:
        return DEFAULT_MAX_CHARS
    return value


def summary_path(root: Path, studio_config: dict[str, Any]) -> Path:
    base = user_context_path(root, studio_config)
    return base.with_name(f"{base.stem}.summary{base.suffix}")


@dataclass(frozen=True)
class UserContextResolution:
    enabled: bool
    text: str | None
    path: Path | None
    loaded: bool


def global_user_context_enabled(studio_config: dict[str, Any]) -> bool:
    uc = studio_config.get("user_context") or {}
    return bool(uc.get("enabled", True))


def session_user_context_enabled(
    studio_config: dict[str, Any],
    *,
    no_user_context: bool = False,
) -> bool:
    if no_user_context:
        return False
    return global_user_context_enabled(studio_config)


def user_context_path(root: Path, studio_config: dict[str, Any]) -> Path:
    uc = studio_config.get("user_context") or {}
    rel = str(uc.get("path") or DEFAULT_USER_CONTEXT_PATH)
    return (root.resolve() / rel).resolve()


def load_user_context_text(root: Path, studio_config: dict[str, Any]) -> str | None:
    path = user_context_path(root, studio_config)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None

    max_chars = user_context_max_chars(studio_config)
    if len(text) <= max_chars:
        return text

    summary_file = summary_path(root, studio_config)
    if summary_file.is_file():
        summary = summary_file.read_text(encoding="utf-8").strip()
        if summary:
            return summary

    return text[:max_chars].rstrip() + "\n\n…（全文は my_context.md。要約は --user-context-summarize）"


def resolve_user_context(
    root: Path,
    studio_config: dict[str, Any],
    *,
    no_user_context: bool = False,
) -> UserContextResolution:
    enabled = session_user_context_enabled(studio_config, no_user_context=no_user_context)
    if not enabled:
        return UserContextResolution(enabled=False, text=None, path=None, loaded=False)
    path = user_context_path(root, studio_config)
    text = load_user_context_text(root, studio_config)
    return UserContextResolution(
        enabled=True,
        text=text,
        path=path if path.is_file() else None,
        loaded=bool(text),
    )


def build_generation_options(
    studio_config: dict[str, Any],
    root: Path,
    *,
    stream: bool,
    temperature: float,
    no_user_context: bool = False,
) -> tuple[dict[str, Any], UserContextResolution]:
    resolution = resolve_user_context(root, studio_config, no_user_context=no_user_context)
    generation: dict[str, Any] = {
        "stream": stream,
        "temperature": temperature,
        "user_context": resolution.enabled,
    }
    return generation, resolution
