"""Assistant API-key availability for Web UI (design.md §8.3 #10, ChatWeb.py 踏襲)."""

from __future__ import annotations

import os
from typing import Any

from studio.loader import RESERVED_ASSISTANTS, load_ai_assistants
from studio.validation import ValidationReport

_ASSISTANT_CLASS_API_KEYS: dict[str, tuple[str, ...]] = {
    "ChatOpenAI": ("OPENAI_API_KEY",),
    "ChatGoogleGenerativeAI": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "ChatAnthropic": ("ANTHROPIC_API_KEY",),
    "ChatGroq": ("GROQ_API_KEY",),
    "ChatMistralAI": ("MISTRAL_API_KEY",),
    "ChatTogether": ("TOGETHER_API_KEY",),
    "ChatXAI": ("XAI_API_KEY",),
    "ChatOpperAI": ("OPPER_API_KEY",),
}


def required_api_keys(assistant_name: str, assistant_cfg: dict[str, Any] | None) -> tuple[str, ...]:
    if assistant_name in RESERVED_ASSISTANTS:
        return ()
    cfg = assistant_cfg or {}
    class_name = cfg.get("class", "")
    module_name = cfg.get("module", "")
    if class_name in _ASSISTANT_CLASS_API_KEYS:
        return _ASSISTANT_CLASS_API_KEYS[class_name]
    module_lower = module_name.lower()
    if "openai" in module_lower:
        return ("OPENAI_API_KEY",)
    if "google" in module_lower or "gemini" in module_lower:
        return ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    if "anthropic" in module_lower:
        return ("ANTHROPIC_API_KEY",)
    if "groq" in module_lower:
        return ("GROQ_API_KEY",)
    if "mistral" in module_lower:
        return ("MISTRAL_API_KEY",)
    if "together" in module_lower:
        return ("TOGETHER_API_KEY",)
    if "xai" in module_lower:
        return ("XAI_API_KEY",)
    if "opper" in module_lower:
        return ("OPPER_API_KEY",)
    return ()


def is_assistant_available(assistant_name: str, assistant_cfg: dict[str, Any] | None) -> bool:
    keys = required_api_keys(assistant_name, assistant_cfg)
    if not keys:
        return True
    return any(bool(os.getenv(key, "").strip()) for key in keys)


def unavailable_reason(assistant_name: str, assistant_cfg: dict[str, Any] | None) -> str:
    keys = required_api_keys(assistant_name, assistant_cfg)
    if not keys:
        return ""
    if is_assistant_available(assistant_name, assistant_cfg):
        return ""
    joined = " / ".join(keys)
    return f"環境変数 {joined} が未設定です"


def load_assistants_catalog(root) -> dict[str, dict[str, Any]]:
    report = ValidationReport()
    return load_ai_assistants(root, report)


def assistant_dropdown_choices(
    assistants: dict[str, dict[str, Any]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (dropdown choices, selectable assistant names)."""
    names = sorted(set(assistants.keys()) | set(RESERVED_ASSISTANTS))
    choices: list[tuple[str, str]] = []
    selectable: list[str] = []
    for name in names:
        cfg = assistants.get(name, {})
        if is_assistant_available(name, cfg):
            choices.append((name, name))
            selectable.append(name)
            continue
        reason = unavailable_reason(name, cfg)
        label = f"{name}（APIキー未設定）"
        choices.append((label, name))
    return choices, selectable


def model_dropdown_choices(assistant_name: str, assistants: dict[str, dict[str, Any]]) -> list[str]:
    if assistant_name in RESERVED_ASSISTANTS:
        return []
    models = assistants.get(assistant_name, {}).get("models") or []
    return [str(model) for model in models]
