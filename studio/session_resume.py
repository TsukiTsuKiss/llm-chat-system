"""Session resume / branch (design.md §7.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from studio.history import RoleHistories
from studio.prompts import build_user_message
from studio.session_report import read_jsonl, session_log_path
from studio.validation import StudioError, StudioValidationError, ValidationReport


@dataclass(frozen=True)
class ResumedSession:
    parent_session_id: str
    org_id: str
    workflow_id: str | None
    step_number: int
    histories: RoleHistories
    replay_messages: list[dict[str, str]]


def load_effective_records(root: Path, session_id: str) -> list[dict[str, Any]]:
    """Merge parent chain + branch jsonl into chronological records."""
    path = session_log_path(root, session_id)
    records = read_jsonl(path)
    if not records:
        return []

    meta = next((r for r in records if r.get("type") == "session_meta"), None)
    parent_id = (meta or {}).get("parent_session_id")
    if not parent_id:
        return records

    parent_records = load_effective_records(root, parent_id)
    parent_body = [r for r in parent_records if r.get("type") != "session_end"]
    child_body = [r for r in records if r.get("type") != "session_meta"]
    return parent_body + child_body


def last_state_snapshot(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    snapshot = None
    for record in records:
        if record.get("type") == "state_snapshot":
            snapshot = record.get("state") or {}
    return snapshot


def rebuild_histories(records: list[dict[str, Any]]) -> RoleHistories:
    histories = RoleHistories()
    pending_user_text = ""

    for record in records:
        record_type = record.get("type")
        if record_type == "user_input":
            pending_user_text = record.get("text") or ""
            continue
        if record_type != "step" or not pending_user_text:
            continue

        talent_id = record.get("talent_id") or ""
        if not talent_id:
            continue
        action = record.get("action") or ""
        text = record.get("text") or ""
        user_message = build_user_message(pending_user_text, action=action)
        history = histories.for_talent(talent_id)
        history.add_message(HumanMessage(content=user_message))
        history.add_message(AIMessage(content=text))

    return histories


def build_replay_messages(
    records: list[dict[str, Any]],
    *,
    talent_names: dict[str, str],
) -> list[dict[str, str]]:
    from studio.web_ui import SPEAKER_EMOJIS, format_step_metrics_line

    messages: list[dict[str, str]] = []
    emoji_index = 0
    talent_emoji: dict[str, str] = {}

    def emoji_for(talent_id: str) -> str:
        nonlocal emoji_index
        if talent_id not in talent_emoji:
            talent_emoji[talent_id] = SPEAKER_EMOJIS[emoji_index % len(SPEAKER_EMOJIS)]
            emoji_index += 1
        return talent_emoji[talent_id]

    meta = next((r for r in records if r.get("type") == "session_meta"), None)
    if meta:
        org = meta.get("organization", "?")
        wf = meta.get("workflow") or "直接送信（全ロール）"
        parent = meta.get("parent_session_id")
        branch = f"（分岐元 `{parent}`）" if parent else ""
        messages.append(
            {
                "role": "assistant",
                "content": f"_ログ再現: {org} / {wf}{branch}_",
            }
        )

    pending_user_text = ""
    for record in records:
        record_type = record.get("type")
        if record_type == "user_input":
            pending_user_text = record.get("text") or ""
            display = pending_user_text
            attachments = record.get("attachments") or []
            if attachments:
                display = f"{display}\n\n📎 添付: {', '.join(attachments)}"
            if display.strip():
                messages.append({"role": "user", "content": display})
            continue
        if record_type != "step" or not pending_user_text:
            continue

        talent_id = record.get("talent_id") or "?"
        display_name = talent_names.get(talent_id, talent_id)
        emoji = emoji_for(talent_id)
        metrics = format_step_metrics_line(record)
        body = record.get("text") or ""
        footer = f"\n\n_{metrics}_" if metrics.strip() else ""
        messages.append(
            {
                "role": "assistant",
                "content": f"{emoji} **{display_name}**\n\n{body}{footer}",
            }
        )

    return messages


def load_resumed_session(root: Path, session_id: str) -> ResumedSession:
    report = ValidationReport()
    session_id = (session_id or "").strip()
    if not session_id:
        report.add(
            StudioError(
                code="E501",
                target="session",
                message="session_id が未指定です",
            )
        )
        raise StudioValidationError(report.errors)

    path = session_log_path(root, session_id)
    if not path.is_file():
        report.add(
            StudioError(
                code="E502",
                target=f"sessions/{session_id}.jsonl",
                message=f"セッション '{session_id}' が見つかりません",
            )
        )
        raise StudioValidationError(report.errors)

    records = load_effective_records(root, session_id)
    meta = next((r for r in records if r.get("type") == "session_meta"), None)
    if meta is None:
        report.add(
            StudioError(
                code="E503",
                target=f"sessions/{session_id}.jsonl",
                message="session_meta がありません",
            )
        )
        raise StudioValidationError(report.errors)

    snapshot = last_state_snapshot(records) or {}
    step_number = int(snapshot.get("step_number") or 0)
    for record in records:
        if record.get("type") == "step":
            step_number = max(step_number, 1)

    org_id = str(meta.get("organization") or "")
    workflow = meta.get("workflow")
    workflow_id = str(workflow).strip() if workflow else None

    talent_names = {
        tid: str(name)
        for tid, name in (meta.get("talents") or {}).items()
    }
    histories = rebuild_histories(records)
    replay_messages = build_replay_messages(records, talent_names=talent_names)

    return ResumedSession(
        parent_session_id=session_id,
        org_id=org_id,
        workflow_id=workflow_id,
        step_number=step_number,
        histories=histories,
        replay_messages=replay_messages,
    )
