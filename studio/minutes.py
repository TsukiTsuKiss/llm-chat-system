"""Structured meeting minutes from session JSONL (design.md §7.3)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from studio.history import ConversationHistory
from studio.loader import load_session_context
from studio.logging import load_model_costs
from studio.session_report import read_jsonl, session_log_path
from studio.session_resume import load_effective_records
from studio.vcs import GitResult, commit_paths


@dataclass(frozen=True)
class MinutesSaveResult:
    ok: bool
    message: str
    path: Path | None = None
    md_path: Path | None = None
    git: GitResult | None = None
    document: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def slugify_topic(text: str, *, fallback: str = "session") -> str:
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^\w\-]+", "", normalized, flags=re.UNICODE)
    normalized = normalized.strip("_")
    return normalized[:64] if normalized else fallback


def default_topic_slug(records: list[dict[str, Any]], session_id: str) -> str:
    for record in records:
        if record.get("type") == "user_input":
            text = str(record.get("text") or "").strip()
            if text:
                return slugify_topic(text[:40], fallback=session_id)
    return slugify_topic(session_id, fallback="session")


def minutes_path(root: Path, org_id: str, topic: str, *, suffix: str = ".json") -> Path:
    slug = slugify_topic(topic, fallback="session")
    return root / "minutes" / org_id / f"{slug}{suffix}"


def document_to_markdown(document: dict[str, Any]) -> str:
    """Human-readable minutes view (derived from JSON document)."""
    topic = str(document.get("topic") or "session")
    updated = str(document.get("updated_at") or "")
    sessions = document.get("source_sessions") or []
    body = document.get("minutes") or {}

    lines: list[str] = [
        f"# 議事録: {topic}",
        "",
        f"- **更新**: {updated}" if updated else "",
    ]
    if sessions:
        lines.append(f"- **元セッション**: {', '.join(str(s) for s in sessions)}")
    lines.append("")

    def section(title: str, items: list[Any], *, bullet: bool = True) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("_（なし）_")
        elif bullet:
            for item in items:
                lines.append(f"- {item}")
        lines.append("")

    section("決定事項", list(body.get("decisions") or []))

    section("未決事項", list(body.get("open_issues") or []))

    lines.append("## アクション")
    lines.append("")
    actions = body.get("actions") or []
    if not actions:
        lines.append("_（なし）_")
    else:
        lines.append("| 担当 | タスク | 期限 |")
        lines.append("| --- | --- | --- |")
        for action in actions:
            if isinstance(action, dict):
                lines.append(
                    f"| {action.get('owner', '')} | {action.get('task', '')} | {action.get('due', '')} |"
                )
            else:
                lines.append(f"| | {action} | |")
    lines.append("")

    lines.append("## 根拠")
    lines.append("")
    evidence = body.get("evidence") or []
    if not evidence:
        lines.append("_（なし）_")
    else:
        for item in evidence:
            if isinstance(item, dict):
                session = item.get("session", "?")
                turns = item.get("turns") or []
                turn_text = ", ".join(str(t) for t in turns)
                lines.append(f"- セッション `{session}` — ターン {turn_text}")
            else:
                lines.append(f"- {item}")
    lines.append("")

    section("次回アジェンダ", list(body.get("next_agenda") or []))

    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def build_transcript(records: list[dict[str, Any]], *, meta: dict[str, Any]) -> str:
    talent_names = meta.get("talents") or {}
    lines: list[str] = []
    turn = 0
    for record in records:
        record_type = record.get("type")
        if record_type == "user_input":
            turn += 1
            text = str(record.get("text") or "").strip()
            if text:
                lines.append(f"[user turn {turn}] {text}")
            continue
        if record_type == "step":
            talent_id = record.get("talent_id") or "?"
            name = talent_names.get(talent_id, talent_id)
            action = record.get("action") or ""
            text = str(record.get("text") or "").strip()
            prefix = f"[{name}/{talent_id} turn {turn}]"
            if action:
                prefix += f" ({action})"
            lines.append(f"{prefix}\n{text}")
    return "\n\n".join(lines)


def _collect_session_ids(records: list[dict[str, Any]], primary_session_id: str) -> list[str]:
    ids: list[str] = []
    for record in records:
        if record.get("type") != "session_meta":
            continue
        sid = record.get("session_id")
        if sid and sid not in ids:
            ids.append(str(sid))
    if primary_session_id not in ids:
        ids.append(primary_session_id)
    return ids


def mock_minutes_document(
    *,
    org_id: str,
    topic: str,
    session_id: str,
    records: list[dict[str, Any]],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_inputs = [str(r.get("text") or "") for r in records if r.get("type") == "user_input"]
    steps = [r for r in records if r.get("type") == "step"]
    source_sessions = _merge_source_sessions(existing, session_id, records)

    decisions = list((existing or {}).get("minutes", {}).get("decisions") or [])
    if user_inputs and user_inputs[0] not in decisions:
        decisions.append(f"議題: {user_inputs[0][:200]}")

    open_issues = list((existing or {}).get("minutes", {}).get("open_issues") or [])
    actions = list((existing or {}).get("minutes", {}).get("actions") or [])
    next_agenda = list((existing or {}).get("minutes", {}).get("next_agenda") or [])
    evidence = list((existing or {}).get("minutes", {}).get("evidence") or [])
    evidence.append({"session": session_id, "turns": list(range(1, max(len(steps), 1) + 1))})

    return {
        "topic": slugify_topic(topic, fallback=session_id),
        "updated_at": _now_iso(),
        "source_sessions": source_sessions,
        "minutes": {
            "decisions": decisions,
            "open_issues": open_issues,
            "actions": actions,
            "evidence": evidence,
            "next_agenda": next_agenda,
        },
    }


def _merge_source_sessions(
    existing: dict[str, Any] | None,
    session_id: str,
    records: list[dict[str, Any]],
) -> list[str]:
    merged: list[str] = []
    for sid in (existing or {}).get("source_sessions") or []:
        if sid not in merged:
            merged.append(str(sid))
    for sid in _collect_session_ids(records, session_id):
        if sid not in merged:
            merged.append(sid)
    return merged


def _parse_minutes_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def generate_minutes_document(
    root: Path,
    org_id: str,
    topic: str,
    session_id: str,
    records: list[dict[str, Any]],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = next((r for r in records if r.get("type") == "session_meta"), {}) or {}
    ctx = load_session_context(org_id, root, workflow_id=meta.get("workflow") or None)

    talent_ids = list(ctx.org.get("talent_ids") or [])
    summarizer_id = talent_ids[0] if talent_ids else None
    mapping = ctx.model_mapping.get(summarizer_id or "", {})
    assistant = mapping.get("assistant", "")

    if assistant == "mock" or not summarizer_id:
        return mock_minutes_document(
            org_id=org_id,
            topic=topic,
            session_id=session_id,
            records=records,
            existing=existing,
        )

    from studio.assistants import invoke_llm_step

    transcript = build_transcript(records, meta=meta)
    existing_json = json.dumps(existing, ensure_ascii=False, indent=2) if existing else "{}"
    system_prompt = (
        "あなたは会議の議事録作成者です。会話ログから構造化議事録 JSON のみを出力してください。"
        "説明文や Markdown は不要です。"
    )
    user_message = (
        f"組織: {org_id}\n"
        f"トピック: {topic}\n"
        f"セッション ID: {session_id}\n\n"
        f"既存議事録（更新ベース）:\n{existing_json}\n\n"
        "次の JSON 形式で出力してください:\n"
        "{\n"
        '  "topic": "...",\n'
        '  "updated_at": "ISO8601",\n'
        '  "source_sessions": ["..."],\n'
        '  "minutes": {\n'
        '    "decisions": ["..."],\n'
        '    "open_issues": ["..."],\n'
        '    "actions": [{"owner":"...","task":"...","due":"YYYY-MM-DD"}],\n'
        '    "evidence": [{"session":"...","turns":[1]}],\n'
        '    "next_agenda": ["..."]\n'
        "  }\n"
        "}\n\n"
        f"会話ログ:\n{transcript}"
    )
    assistant_cfg = ctx.assistants[assistant]
    result = invoke_llm_step(
        assistant_name=assistant,
        assistant_cfg=assistant_cfg,
        model=mapping.get("model", ""),
        system_prompt=system_prompt,
        user_message=user_message,
        history=ConversationHistory(),
        temperature=0.3,
        stream=False,
        costs=load_model_costs(root),
    )
    parsed = _parse_minutes_json(result.text)
    if parsed and parsed.get("minutes"):
        parsed["topic"] = slugify_topic(str(parsed.get("topic") or topic), fallback=session_id)
        parsed["updated_at"] = _now_iso()
        parsed["source_sessions"] = _merge_source_sessions(existing, session_id, records)
        return parsed

    doc = mock_minutes_document(
        org_id=org_id,
        topic=topic,
        session_id=session_id,
        records=records,
        existing=existing,
    )
    doc["_llm_parse_fallback"] = True
    return doc


def load_existing_minutes(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def validate_minutes_document(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("topic"), str) or not data["topic"].strip():
        errors.append("topic が必要です")
    minutes = data.get("minutes")
    if not isinstance(minutes, dict):
        errors.append("minutes オブジェクトが必要です")
        return errors
    for key in ("decisions", "open_issues", "actions", "evidence", "next_agenda"):
        if key not in minutes:
            errors.append(f"minutes.{key} が必要です")
    return errors


def save_minutes_document(
    root: Path,
    org_id: str,
    topic: str,
    document: dict[str, Any],
) -> tuple[Path, Path]:
    json_path = minutes_path(root, org_id, topic, suffix=".json")
    md_path = minutes_path(root, org_id, topic, suffix=".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(document_to_markdown(document), encoding="utf-8")
    return json_path, md_path


def save_minutes_from_session(
    root: Path,
    session_id: str,
    *,
    topic: str | None = None,
    commit: bool = True,
) -> MinutesSaveResult:
    session_id = (session_id or "").strip()
    if not session_id:
        return MinutesSaveResult(False, "session_id が未指定です")

    log_path = session_log_path(root, session_id)
    if not log_path.is_file():
        return MinutesSaveResult(False, f"セッション `{session_id}` が見つかりません")

    records = load_effective_records(root, session_id)
    meta = next((r for r in records if r.get("type") == "session_meta"), None)
    if meta is None:
        return MinutesSaveResult(False, "session_meta がありません")

    org_id = str(meta.get("organization") or "").strip()
    if not org_id:
        return MinutesSaveResult(False, "organization が session_meta にありません")

    topic_slug = slugify_topic(topic, fallback="") if topic else ""
    if not topic_slug:
        topic_slug = default_topic_slug(records, session_id)

    path = minutes_path(root, org_id, topic_slug)
    existing = load_existing_minutes(path)
    document = generate_minutes_document(
        root,
        org_id,
        topic_slug,
        session_id,
        records,
        existing=existing,
    )
    errors = validate_minutes_document(document)
    if errors:
        return MinutesSaveResult(False, "議事録 JSON が不正です: " + "; ".join(errors))

    saved_json, saved_md = save_minutes_document(root, org_id, topic_slug, document)
    git_result = None
    json_rel = saved_json.relative_to(root).as_posix()
    md_rel = saved_md.relative_to(root).as_posix()
    message = f"`{json_rel}` と `{md_rel}` を保存しました"
    if commit:
        commit_msg = f"minutes({org_id}/{document['topic']}): update from session {session_id}"
        git_result = commit_paths(root, [saved_json, saved_md], commit_msg)
        # 運用 UI では Git 成否を message に載せない（design.md 7.3.1）

    return MinutesSaveResult(
        True,
        message,
        path=saved_json,
        md_path=saved_md,
        git=git_result,
        document=document,
    )
