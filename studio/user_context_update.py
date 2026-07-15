"""User context draft generation and approval merge (design.md Appendix D.7–D.8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from studio.history import ConversationHistory
from studio.loader import load_session_context
from studio.logging import load_model_costs
from studio.minutes import build_transcript
from studio.session_report import session_log_path
from studio.session_resume import load_effective_records
from studio.user_context import summary_path, user_context_max_chars, user_context_path

DEFAULT_DRAFTS_DIR = "user_context/drafts"
ACCUMULATION_SECTION = "## 蓄積メモ"
DRAFT_PROPOSAL_SECTION = "## 提案追記（蓄積メモへ）"


@dataclass(frozen=True)
class ContextUpdateResult:
    ok: bool
    message: str
    path: Path | None = None
    text: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def draft_path(root: Path, session_id: str) -> Path:
    return root.resolve() / DEFAULT_DRAFTS_DIR / f"{session_id}.md"


def _extract_proposal_lines(draft_text: str) -> list[str]:
    lines = draft_text.splitlines()
    in_section = False
    proposals: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == DRAFT_PROPOSAL_SECTION
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            proposals.append(stripped)
    return proposals


def merge_draft_into_context(current: str, draft_text: str, session_id: str) -> str:
    proposals = _extract_proposal_lines(draft_text)
    if not proposals:
        raise ValueError("提案追記が draft に含まれていません")

    stamp = _now_iso()
    block_lines = [f"", f"### {stamp}（session `{session_id}`）", ""]
    block_lines.extend(proposals)
    block = "\n".join(block_lines)

    text = current.rstrip()
    if ACCUMULATION_SECTION in text:
        parts = text.split(ACCUMULATION_SECTION, 1)
        head = parts[0].rstrip()
        tail = parts[1]
        return f"{head}\n{ACCUMULATION_SECTION}{tail.rstrip()}{block}\n"
    return f"{text}\n{ACCUMULATION_SECTION}{block}\n"


def mock_context_draft(
    *,
    session_id: str,
    records: list[dict[str, Any]],
) -> str:
    user_inputs = [
        str(r.get("text") or "").strip()
        for r in records
        if r.get("type") == "user_input" and str(r.get("text") or "").strip()
    ]
    topic = user_inputs[0][:120] if user_inputs else "（議題なし）"
    insight = user_inputs[-1][:200] if user_inputs else "（ユーザー発言なし）"

    return (
        "# ユーザーコンテキスト更新案\n\n"
        f"- **セッション**: `{session_id}`\n"
        f"- **生成**: {_now_iso()}\n\n"
        f"{DRAFT_PROPOSAL_SECTION}\n\n"
        f"- （セッション `{session_id}`）議題: {topic}\n"
        f"- （セッション `{session_id}`）気づき: {insight}\n\n"
        "## 根拠\n\n"
        f"- `sessions/{session_id}.jsonl`\n"
    )


def generate_context_draft_text(
    root: Path,
    session_id: str,
    records: list[dict[str, Any]],
    *,
    current_context: str | None = None,
) -> str:
    meta = next((r for r in records if r.get("type") == "session_meta"), {}) or {}
    org_id = str(meta.get("organization") or "").strip() or "solo"
    ctx = load_session_context(org_id, root, workflow_id=meta.get("workflow") or None)

    talent_ids = list(ctx.org.get("talent_ids") or [])
    summarizer_id = talent_ids[0] if talent_ids else None
    mapping = ctx.model_mapping.get(summarizer_id or "", {})
    assistant = mapping.get("assistant", "")

    if assistant == "mock" or not summarizer_id:
        return mock_context_draft(session_id=session_id, records=records)

    from studio.assistants import invoke_llm_step

    transcript = build_transcript(records, meta=meta)
    current = (current_context or "").strip() or "（未作成）"
    system_prompt = (
        "あなたはユーザーコンテキスト（my_context）の編集者です。"
        "会話ログから、ユーザー本人向けの追記案だけを Markdown で出力してください。"
        "既存の用語定義と矛盾する内容は提案しないでください。"
    )
    user_message = (
        f"セッション: {session_id}\n\n"
        f"現在の my_context.md:\n```markdown\n{current}\n```\n\n"
        "出力形式:\n"
        f"# ユーザーコンテキスト更新案\n"
        f"- セッション: `{session_id}`\n"
        f"- 生成: （ISO8601 日時）\n\n"
        f"{DRAFT_PROPOSAL_SECTION}\n"
        "- （箇条書きで 1〜5 件。承認後に蓄積メモへ追記する想定）\n\n"
        "## 根拠\n"
        f"- sessions/{session_id}.jsonl\n\n"
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
    text = (result.text or "").strip()
    if not text or DRAFT_PROPOSAL_SECTION not in text:
        return mock_context_draft(session_id=session_id, records=records)
    return text + ("\n" if not text.endswith("\n") else "")


def save_context_draft_from_session(root: Path, session_id: str) -> ContextUpdateResult:
    root = root.resolve()
    session_id = (session_id or "").strip()
    if not session_id:
        return ContextUpdateResult(False, "session_id が未指定です")

    log_path = session_log_path(root, session_id)
    if not log_path.is_file():
        return ContextUpdateResult(False, f"セッション `{session_id}` が見つかりません")

    from studio.loader import load_studio_config

    studio_config = load_studio_config(root)
    current_path = user_context_path(root, studio_config)
    current_context = current_path.read_text(encoding="utf-8") if current_path.is_file() else None

    records = load_effective_records(root, session_id)
    draft_text = generate_context_draft_text(
        root,
        session_id,
        records,
        current_context=current_context,
    )
    path = draft_path(root, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft_text, encoding="utf-8")
    rel = path.relative_to(root).as_posix()
    return ContextUpdateResult(True, f"`{rel}` に更新案を保存しました", path=path, text=draft_text)


def apply_context_draft(root: Path, session_id: str) -> ContextUpdateResult:
    root = root.resolve()
    session_id = (session_id or "").strip()
    if not session_id:
        return ContextUpdateResult(False, "session_id が未指定です")

    draft_file = draft_path(root, session_id)
    if not draft_file.is_file():
        return ContextUpdateResult(False, f"更新案 `{session_id}.md` が見つかりません。先に生成してください")

    from studio.loader import load_studio_config

    studio_config = load_studio_config(root)
    target = user_context_path(root, studio_config)
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    draft_text = draft_file.read_text(encoding="utf-8")

    try:
        merged = merge_draft_into_context(current, draft_text, session_id)
    except ValueError as exc:
        return ContextUpdateResult(False, str(exc))

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(merged, encoding="utf-8")
    rel = target.relative_to(root).as_posix()
    return ContextUpdateResult(True, f"`{rel}` に追記しました", path=target, text=merged)


def mock_summary_text(source_text: str, *, max_chars: int) -> str:
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    bullets: list[str] = []
    for line in lines:
        if line.startswith("#"):
            continue
        if line.startswith("- "):
            bullets.append(line)
        if len(bullets) >= 12:
            break
    if not bullets:
        excerpt = source_text[: max_chars // 2].strip()
        bullets = [f"- {excerpt[:200]}"] if excerpt else ["- （要約対象なし）"]
    body = "\n".join(bullets[:12])
    return (
        "# ユーザーコンテキスト要約\n\n"
        f"- **生成**: {_now_iso()}\n"
        f"- **元文字数**: {len(source_text)}\n"
        f"- **上限**: {max_chars}\n\n"
        "## 要約\n\n"
        f"{body}\n"
    )


def generate_summary_draft_text(
    root: Path,
    source_text: str,
    *,
    max_chars: int,
    studio_config: dict[str, Any],
) -> str:
    org_id = str(studio_config.get("default_org") or "solo")
    try:
        ctx = load_session_context(org_id, root, workflow_id=None)
    except Exception:
        return mock_summary_text(source_text, max_chars=max_chars)

    talent_ids = list(ctx.org.get("talent_ids") or [])
    summarizer_id = talent_ids[0] if talent_ids else None
    mapping = ctx.model_mapping.get(summarizer_id or "", {})
    assistant = mapping.get("assistant", "")

    if assistant == "mock" or not summarizer_id:
        return mock_summary_text(source_text, max_chars=max_chars)

    from studio.assistants import invoke_llm_step

    system_prompt = (
        "あなたはユーザーコンテキストの要約者です。"
        "元テキストの用語定義・関心・好みを落とさず、注入用の短い Markdown を出力してください。"
    )
    user_message = (
        f"文字数上限: {max_chars}\n\n"
        "元の my_context.md:\n"
        f"```markdown\n{source_text}\n```\n\n"
        "出力: 見出し `# ユーザーコンテキスト要約` と箇条書き中心の短い Markdown のみ。"
    )
    assistant_cfg = ctx.assistants[assistant]
    result = invoke_llm_step(
        assistant_name=assistant,
        assistant_cfg=assistant_cfg,
        model=mapping.get("model", ""),
        system_prompt=system_prompt,
        user_message=user_message,
        history=ConversationHistory(),
        temperature=0.2,
        stream=False,
        costs=load_model_costs(root),
    )
    text = (result.text or "").strip()
    if not text:
        return mock_summary_text(source_text, max_chars=max_chars)
    return text + ("\n" if not text.endswith("\n") else "")


def save_summary_from_context(root: Path) -> ContextUpdateResult:
    root = root.resolve()
    from studio.loader import load_studio_config

    studio_config = load_studio_config(root)
    source_path = user_context_path(root, studio_config)
    if not source_path.is_file():
        return ContextUpdateResult(False, "`my_context.md` が見つかりません")

    source_text = source_path.read_text(encoding="utf-8").strip()
    if not source_text:
        return ContextUpdateResult(False, "`my_context.md` が空です")

    max_chars = user_context_max_chars(studio_config)
    summary_text = generate_summary_draft_text(
        root,
        source_text,
        max_chars=max_chars,
        studio_config=studio_config,
    )
    out_path = summary_path(root, studio_config)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(summary_text, encoding="utf-8")
    rel = out_path.relative_to(root).as_posix()
    return ContextUpdateResult(True, f"`{rel}` に要約を保存しました", path=out_path, text=summary_text)


def load_draft_preview(root: Path, session_id: str, *, max_chars: int = 1200) -> str:
    path = draft_path(root, session_id)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n…（続きはファイルを参照）\n"
