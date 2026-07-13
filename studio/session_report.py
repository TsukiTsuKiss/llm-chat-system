"""Session JSONL listing and Markdown report generation (design.md §7.1, §8.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from studio.display import format_by_model_markdown_table, format_step_metrics_line

DIRECT_WORKFLOW_LABEL = "直接送信"

FlowTheme = Literal["light", "dark"]

_MERMAID_THEME_VARS: dict[FlowTheme, dict[str, Any]] = {
    "light": {
        "primaryColor": "#e2e8f0",
        "primaryTextColor": "#0f172a",
        "primaryBorderColor": "#64748b",
        "lineColor": "#475569",
        "secondaryColor": "#cbd5e1",
        "tertiaryColor": "#f8fafc",
        "mainBkg": "#e2e8f0",
        "nodeBorder": "#64748b",
        "clusterBkg": "#f1f5f9",
        "titleColor": "#0f172a",
        "edgeLabelBackground": "#ffffff",
        "textColor": "#0f172a",
        "nodeTextColor": "#0f172a",
    },
    "dark": {
        "darkMode": True,
        "background": "#0f172a",
        "primaryColor": "#334155",
        "primaryTextColor": "#f8fafc",
        "primaryBorderColor": "#94a3b8",
        "lineColor": "#cbd5e1",
        "secondaryColor": "#475569",
        "tertiaryColor": "#64748b",
        "mainBkg": "#334155",
        "nodeBorder": "#94a3b8",
        "clusterBkg": "#1e293b",
        "titleColor": "#f8fafc",
        "edgeLabelBackground": "#334155",
        "textColor": "#f8fafc",
        "nodeTextColor": "#f8fafc",
    },
}


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    organization: str
    workflow: str | None
    parent_session_id: str | None
    started_at: str
    label: str


def parse_session_timestamp(session_id: str) -> str:
    try:
        dt = datetime.strptime(session_id, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return session_id


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def read_session_meta(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") == "session_meta":
                return record
            return None
    return None


def session_log_path(root: Path, session_id: str) -> Path:
    return Path(root) / "sessions" / f"{session_id}.jsonl"


def format_session_label(
    session_id: str,
    organization: str,
    workflow: str | None,
    *,
    parent_session_id: str | None = None,
) -> str:
    started = parse_session_timestamp(session_id)
    wf = workflow or DIRECT_WORKFLOW_LABEL
    branch = f" ← {parent_session_id}" if parent_session_id else ""
    return f"{started} | {organization} | {wf} | {session_id}{branch}"


def summarize_session(path: Path) -> SessionSummary | None:
    meta = read_session_meta(path)
    if meta is None:
        return None
    session_id = path.stem
    organization = str(meta.get("organization") or "")
    workflow = meta.get("workflow")
    parent = meta.get("parent_session_id")
    return SessionSummary(
        session_id=session_id,
        organization=organization,
        workflow=workflow if workflow else None,
        parent_session_id=parent if parent else None,
        started_at=parse_session_timestamp(session_id),
        label=format_session_label(session_id, organization, workflow, parent_session_id=parent),
    )


def list_sessions(root: Path) -> list[SessionSummary]:
    sessions_dir = Path(root) / "sessions"
    if not sessions_dir.is_dir():
        return []
    summaries: list[SessionSummary] = []
    for path in sessions_dir.glob("*.jsonl"):
        summary = summarize_session(path)
        if summary is not None:
            summaries.append(summary)
    return sorted(summaries, key=lambda item: item.session_id, reverse=True)


def session_dropdown_choices(root: Path) -> list[tuple[str, str]]:
    return [(item.label, item.session_id) for item in list_sessions(root)]


def _workflow_label(workflow: str | None) -> str:
    return workflow if workflow else DIRECT_WORKFLOW_LABEL


def _talent_display_name(meta: dict[str, Any], talent_id: str) -> str:
    talents = meta.get("talents") or {}
    return str(talents.get(talent_id) or talent_id)


def _mermaid_init_line(flow_theme: FlowTheme) -> str:
    payload = {"theme": "base", "themeVariables": _MERMAID_THEME_VARS[flow_theme]}
    return f"%%{{init: {json.dumps(payload, ensure_ascii=False)} }}%%"


def _build_mermaid_flow(
    records: list[dict[str, Any]],
    *,
    flow_theme: FlowTheme = "light",
) -> str:
    lines = ["```mermaid", _mermaid_init_line(flow_theme), "flowchart TD"]
    node_counter = 0
    prev_node: str | None = None
    parallel_buffer: list[dict[str, Any]] = []

    def append_node(label: str) -> str:
        nonlocal node_counter
        node_counter += 1
        node_id = f"N{node_counter}"
        safe = label.replace('"', "'")
        lines.append(f'  {node_id}["{safe}"]')
        return node_id

    def link(from_id: str | None, to_id: str) -> None:
        if from_id:
            lines.append(f"  {from_id} --> {to_id}")

    def flush_parallel() -> None:
        nonlocal prev_node, parallel_buffer
        if not parallel_buffer:
            return
        if len(parallel_buffer) == 1:
            step = parallel_buffer[0]
            node = append_node(f"🤖 {step.get('talent_id', '?')}")
            link(prev_node, node)
            prev_node = node
        else:
            fork = append_node("⚡ parallel")
            link(prev_node, fork)
            join = append_node("⚡ sync")
            for step in parallel_buffer:
                node = append_node(f"🤖 {step.get('talent_id', '?')}")
                lines.append(f"  {fork} --> {node}")
                lines.append(f"  {node} --> {join}")
            prev_node = join
        parallel_buffer = []

    for record in records:
        record_type = record.get("type")
        if record_type == "user_input":
            flush_parallel()
            text = (record.get("text") or "").replace("\n", " ")
            if len(text) > 40:
                text = text[:37] + "..."
            label = text.replace('"', "'") or "user"
            node = append_node(f"👤 {label}")
            link(prev_node, node)
            prev_node = node
        elif record_type == "step":
            if record.get("phase_type") == "parallel":
                parallel_buffer.append(record)
                continue
            flush_parallel()
            node = append_node(f"🤖 {record.get('talent_id', '?')}")
            link(prev_node, node)
            prev_node = node

    flush_parallel()
    if node_counter == 0:
        lines.append('  empty["（記録なし）"]')
    lines.append("```")
    return "\n".join(lines)


def _build_step_summary_table(records: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    rows: list[str] = [
        "",
        "| # | 人材 | assistant / model | 応答時間 | トークン |",
        "|---:|---|---|---:|---|",
    ]
    step_no = 0
    for record in records:
        if record.get("type") != "step":
            continue
        step_no += 1
        talent_id = record.get("talent_id", "?")
        display = _talent_display_name(meta, talent_id)
        assistant = record.get("assistant") or "?"
        model = record.get("model")
        model_label = f"{assistant}/{model}" if model else assistant
        metrics = format_step_metrics_line(record)
        elapsed = float(record.get("elapsed") or 0.0)
        tokens = record.get("tokens") or {}
        token_label = f"in={tokens.get('in', 0)} out={tokens.get('out', 0)}"
        rows.append(
            f"| {step_no} | {display} (`{talent_id}`) | {model_label} | {elapsed:.3f}s | {token_label} |"
        )
        _ = metrics
    if step_no == 0:
        return ""
    return "\n".join(rows)


def generate_session_markdown(
    records: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    flow_theme: FlowTheme = "light",
) -> str:
    if not records:
        return "_セッションログが空です_"

    meta = next((record for record in records if record.get("type") == "session_meta"), None)
    if meta is None:
        return "_session_meta が見つかりません_"

    resolved_id = (session_id or meta.get("session_id") or "").strip()
    if not resolved_id:
        for record in records:
            if record.get("type") == "session_end" and record.get("log_path"):
                resolved_id = Path(str(record["log_path"])).stem
                break
    if not resolved_id:
        resolved_id = "?"

    organization = meta.get("organization") or "?"
    workflow = _workflow_label(meta.get("workflow"))
    generation = meta.get("generation") or {}
    parent = meta.get("parent_session_id")

    lines = [
        f"# セッションレポート `{resolved_id}`",
        "",
        "## メタデータ",
        "",
        f"- **組織**: {organization}",
        f"- **ワークフロー**: {workflow}",
        f"- **開始**: {parse_session_timestamp(str(resolved_id))}",
    ]
    if parent:
        lines.append(f"- **親セッション**: `{parent}`")
    if generation:
        stream = generation.get("stream")
        temperature = generation.get("temperature")
        lines.append(f"- **stream**: {stream}")
        lines.append(f"- **temperature**: {temperature}")

    talents = meta.get("talents") or {}
    if talents:
        lines.extend(["", "### 参加人材", ""])
        for talent_id, name in talents.items():
            models = (meta.get("models") or {}).get(talent_id, {})
            assistant = models.get("assistant", "?")
            model = models.get("model")
            model_part = f" / {model}" if model else ""
            lines.append(f"- {name} (`{talent_id}`) — {assistant}{model_part}")

    lines.extend(["", "## フロー", "", _build_mermaid_flow(records, flow_theme=flow_theme)])

    table = _build_step_summary_table(records, meta)
    if table:
        lines.extend(["", "## 応答時間サマリ", table])

    lines.extend(["", "## 会話ログ", ""])
    lines.append("_`sessions/<id>.jsonl` から生成した Markdown レポートです（生 JSONL ではありません）_")
    lines.append("")
    turn = 0
    for record in records:
        record_type = record.get("type")
        if record_type == "user_input":
            turn += 1
            text = record.get("text") or ""
            attachments = record.get("attachments") or []
            lines.append(f"### {turn}. ユーザー")
            lines.append("")
            lines.append(text)
            if attachments:
                lines.append("")
                lines.append(f"📎 添付: {', '.join(attachments)}")
            lines.append("")
        elif record_type == "step":
            talent_id = record.get("talent_id", "?")
            display = _talent_display_name(meta, talent_id)
            action = record.get("action") or ""
            heading = f"### {display} (`{talent_id}`)"
            if action:
                heading += f" — {action}"
            lines.append(heading)
            lines.append("")
            lines.append(record.get("text") or "")
            lines.append("")
            lines.append(f"_{format_step_metrics_line(record)}_")
            lines.append("")

    end_record = next((record for record in reversed(records) if record.get("type") == "session_end"), None)
    if end_record:
        lines.extend(["", "## セッション終了", ""])
        lines.append(
            f"- **total_elapsed**: {float(end_record.get('total_elapsed') or 0.0):.3f}s"
        )
        lines.append(f"- **total_cost**: ${float(end_record.get('total_cost') or 0.0):.6f}")
        table = format_by_model_markdown_table(end_record.get("by_model") or {})
        if table:
            lines.extend(["", "### by_model", table])

    return "\n".join(lines).strip() + "\n"


def load_session_markdown(
    root: Path,
    session_id: str,
    *,
    flow_theme: FlowTheme = "light",
) -> str:
    if not session_id:
        return "_セッションを選択してください_"
    path = session_log_path(root, session_id)
    if not path.is_file():
        return f"_ログが見つかりません: `{path}`_"
    return generate_session_markdown(
        read_jsonl(path),
        session_id=session_id,
        flow_theme=flow_theme,
    )


def export_session_markdown(
    root: Path,
    session_id: str,
    *,
    flow_theme: FlowTheme = "light",
) -> Path:
    root = Path(root)
    exports_dir = root / "sessions" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    markdown = load_session_markdown(root, session_id, flow_theme=flow_theme)
    out_path = exports_dir / f"{session_id}.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path
