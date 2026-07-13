"""Prompt assembly (design.md 5.1)."""

from __future__ import annotations

from typing import Any


def build_org_context(org: dict[str, Any], org_id: str) -> str:
    lines: list[str] = []
    display = org.get("name") or org_id
    lines.append(f"【所属組織】{display}")
    if org.get("mission"):
        lines.append(f"【ミッション】{org['mission']}")
    culture = org.get("culture") or []
    if culture:
        lines.append("【文化・行動規範】")
        lines.extend(f"- {item}" for item in culture)
    return "\n".join(lines)


def build_system_prompt(
    talent: dict[str, Any],
    org: dict[str, Any],
    org_id: str,
    talent_id: str,
) -> str:
    parts: list[str] = []
    if talent.get("personality"):
        parts.append(talent["personality"])
    parts.append(talent["system_prompt"])

    mission_or_culture = org.get("mission") or org.get("culture")
    if mission_or_culture:
        parts.append(build_org_context(org, org_id))

    common = org.get("common_directives") or []
    if common:
        parts.append("【共通指示】")
        parts.extend(f"- {item}" for item in common)

    role_directives = (org.get("role_directives") or {}).get(talent_id) or []
    if role_directives:
        parts.append("【個別指示】")
        parts.extend(f"- {item}" for item in role_directives)

    return "\n\n".join(parts)


def build_user_message(
    user_text: str,
    *,
    action: str = "",
    attachment_context: str = "",
    prior_responses: list[tuple[str, str]] | None = None,
) -> str:
    parts: list[str] = [user_text]

    if prior_responses:
        parts.append("\n--- 前の発言 ---")
        for talent_id, text in prior_responses:
            parts.append(f"{talent_id}: {text}")

    if action:
        parts.append(f"\nあなたへの指示: {action}")

    if attachment_context:
        parts.append("\n--- 添付ファイル ---")
        parts.append(attachment_context)

    return "\n".join(parts)
