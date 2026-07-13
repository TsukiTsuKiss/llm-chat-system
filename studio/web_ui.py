"""Gradio chat display helpers for MultiRoleStudioWeb (design.md §6.3, §8.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterator

from studio.assistants import MockAssistant
from studio.display import format_session_end_lines, format_step_metrics_line
from studio.engine import EngineEvent, SessionEngine
from studio.loader import SessionContext, load_session_context, read_attachment_files
from studio.validation import StudioValidationError
from web_input_utils import normalize_uploaded_files

DIRECT_WORKFLOW_LABEL = "直接送信（全ロール）"
DIRECT_WORKFLOW_VALUE = ""

SPEAKER_EMOJIS = [
    "🔵", "🟠", "🟢", "🟣",
    "🔴", "🟡", "🟤", "⚫",
    "🔷", "🚨", "💠", "🟩",
]

UIUpdate = tuple[list[dict[str, str]], str, bool, str, bool]

IDLE_STATUS = "待機中（メッセージを入力してください）"
FILE_ONLY_DEFAULT = "添付ファイルの内容を要約してください。"


def list_organizations(root: Path) -> list[str]:
    org_dir = root / "organizations"
    if not org_dir.is_dir():
        return []
    return sorted(
        name.name
        for name in org_dir.iterdir()
        if name.is_dir() and (name / "config.json").is_file()
    )


def list_workflows(root: Path) -> list[str]:
    wf_dir = root / "workflows"
    if not wf_dir.is_dir():
        return []
    return sorted(path.stem for path in wf_dir.glob("*.json"))


def workflow_dropdown_choices(root: Path) -> list[tuple[str, str]]:
    return [(DIRECT_WORKFLOW_LABEL, DIRECT_WORKFLOW_VALUE)] + [
        (wf_id, wf_id) for wf_id in list_workflows(root)
    ]


def upload_limits_from_config(studio_config: dict | None) -> dict[str, int]:
    limits = (studio_config or {}).get("upload_limits")
    if isinstance(limits, dict):
        return limits
    return {}


def gradio_file_paths(files) -> list[Path]:
    return [Path(path) for path in normalize_uploaded_files(files)]


def resolve_user_input_with_attachments(
    user_text: str,
    files,
    limits: dict[str, int],
) -> tuple[str, str, str, list[str]]:
    """Resolve prompt text, chat display text, attachment context, and file names."""
    text = (user_text or "").strip()
    paths = gradio_file_paths(files)
    attachment_context = ""
    attachment_names: list[str] = []

    if paths:
        attachment_context, report = read_attachment_files(paths, limits)
        if not report.ok:
            raise StudioValidationError(report.errors)
        attachment_names = [path.name for path in paths]

    if not text and attachment_names:
        text = FILE_ONLY_DEFAULT

    if not text:
        return "", "", "", []

    display = text
    if attachment_names:
        display = f"{text}\n\n📎 添付: {', '.join(attachment_names)}"

    return text, display, attachment_context, attachment_names


def talents_markdown(ctx: SessionContext) -> str:
    lines = ["**参加人材**", ""]
    for talent_id in ctx.org.get("talent_ids") or []:
        talent = ctx.talents.get(talent_id, {})
        name = talent.get("name", talent_id)
        mapping = ctx.model_mapping.get(talent_id, {})
        assistant = mapping.get("assistant", "?")
        model = mapping.get("model")
        model_part = f" / {model}" if model else ""
        lines.append(f"- {name} (`{talent_id}`) — {assistant}{model_part}")
    if len(lines) == 2:
        lines.append("（なし）")
    return "\n".join(lines)


@dataclass
class PendingInteraction:
    kind: str
    event: EngineEvent
    generator: Iterator[EngineEvent]


@dataclass
class ChatEventRenderer:
    """Convert engine events into Gradio Chatbot messages (type='messages')."""

    messages: list[dict[str, str]] = field(default_factory=list)
    _emoji_map: dict[str, str] = field(default_factory=dict)
    _active_idx: int | None = None
    _last_display_name: dict[str, str] = field(default_factory=dict)

    def copy_messages(self) -> list[dict[str, str]]:
        return [dict(message) for message in self.messages]

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def _emoji_for(self, talent_id: str) -> str:
        if talent_id not in self._emoji_map:
            self._emoji_map[talent_id] = SPEAKER_EMOJIS[len(self._emoji_map) % len(SPEAKER_EMOJIS)]
        return self._emoji_map[talent_id]

    def _assistant_header(self, display_name: str, talent_id: str) -> str:
        return f"{self._emoji_for(talent_id)} **{display_name}**"

    def _start_assistant_bubble(self, display_name: str, talent_id: str, *, placeholder: str = "") -> None:
        self._last_display_name[talent_id] = display_name
        header = self._assistant_header(display_name, talent_id)
        body = f"\n\n{placeholder}" if placeholder else ""
        self.messages.append({"role": "assistant", "content": f"{header}{body}"})
        self._active_idx = len(self.messages) - 1

    def _append_active(self, text: str) -> None:
        if self._active_idx is None:
            return
        self.messages[self._active_idx]["content"] += text

    def _set_active_body(
        self,
        display_name: str,
        talent_id: str,
        text: str,
        metrics: str = "",
    ) -> None:
        header = self._assistant_header(display_name, talent_id)
        footer = f"\n\n_{metrics}_" if metrics else ""
        if self._active_idx is not None:
            self.messages[self._active_idx]["content"] = f"{header}\n\n{text}{footer}"
        else:
            self.messages.append({"role": "assistant", "content": f"{header}\n\n{text}{footer}"})
        self._active_idx = None

    def _add_system_note(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": f"_{text}_"})

    def apply(self, event: EngineEvent) -> str | None:
        if event.type == "session_start":
            payload = event.payload
            wf = payload.get("workflow") or DIRECT_WORKFLOW_LABEL
            self._add_system_note(
                f"セッション開始 `{payload.get('session_id')}` — {payload.get('org')} / {wf}"
            )
            return None

        if event.type == "phase_start" and not event.payload.get("phase_end"):
            phase_type = event.payload.get("phase_type", "serial")
            iteration = event.payload.get("iteration")
            suffix = f"（反復 {iteration}）" if iteration else ""
            self._add_system_note(f"phase: {phase_type}{suffix}")
            return None

        if event.type == "loop_check":
            payload = event.payload
            self._add_system_note(
                f"loop 反復 {payload.get('iteration')}: "
                f"{payload.get('exit_type')} → {payload.get('result')}"
            )
            return None

        if event.type == "step_start":
            payload = event.payload
            self._start_assistant_bubble(
                payload.get("display_name", payload.get("talent_id", "?")),
                payload.get("talent_id", "?"),
                placeholder="考え中…",
            )
            return None

        if event.type == "chunk":
            self._append_active(event.payload.get("text", ""))
            return None

        if event.type == "step_done":
            payload = event.payload
            metrics = format_step_metrics_line(payload)
            talent_id = payload.get("talent_id", "?")
            display_name = payload.get("display_name") or self._last_display_name.get(talent_id, talent_id)
            self._set_active_body(display_name, talent_id, payload.get("text", ""), metrics=metrics)
            return None

        if event.type == "step_error":
            payload = event.payload
            self._add_system_note(f"❌ {payload.get('talent_id')}: {payload.get('error')}")
            self._active_idx = None
            return None

        if event.type == "session_done":
            for line in format_session_end_lines(event.payload):
                if line.strip():
                    self._add_system_note(line.strip())
            return None

        if event.type == "await_text":
            payload = event.payload
            briefing = payload.get("briefing") or ""
            name = payload.get("display_name", payload.get("talent_id", "human"))
            hint = f"**{name}** として発言してください。"
            if briefing:
                hint = f"{hint}\n\n{briefing}"
            self._add_system_note(hint)
            return "await_text"

        if event.type == "await_choice":
            prompt = event.payload.get("prompt", "続けますか？")
            self._add_system_note(f"{prompt}（続行 / 終了）")
            return "await_choice"

        return None


@dataclass
class WebSession:
    root: Path
    org_id: str = ""
    workflow_id: str | None = None
    stream: bool = True
    temperature: float = 0.7
    engine: SessionEngine | None = None
    pending: PendingInteraction | None = None
    renderer: ChatEventRenderer = field(default_factory=ChatEventRenderer)

    def close_engine(self) -> str:
        if self.engine is None or self.engine.state is None or not self.engine.state.started:
            return ""
        end_event = self.engine.finish()
        lines = format_session_end_lines(end_event.payload)
        return "\n".join(line.strip() for line in lines if line.strip())

    def reset_chat(self) -> str:
        summary = self.close_engine()
        self.engine = None
        self.pending = None
        self.renderer = ChatEventRenderer()
        return summary

    def load_context(self, org_id: str, workflow_value: str) -> SessionContext:
        workflow_id = workflow_value or None
        return load_session_context(org_id, self.root, workflow_id=workflow_id)

    def ensure_engine(self, org_id: str, workflow_value: str, stream: bool, temperature: float) -> None:
        workflow_id = workflow_value or None
        if (
            self.engine is not None
            and self.org_id == org_id
            and self.workflow_id == workflow_id
        ):
            self.stream = stream
            self.temperature = temperature
            if self.engine.state is not None:
                self.engine.state.stream = stream
                self.engine.state.temperature = temperature
            return

        self.reset_chat()
        ctx = self.load_context(org_id, workflow_value)
        MockAssistant.reset()
        self.engine = SessionEngine(ctx)
        self.org_id = org_id
        self.workflow_id = workflow_id
        self.stream = stream
        self.temperature = temperature


def _status_from_event(event: EngineEvent) -> str:
    if event.type == "session_start":
        return f"セッション {event.payload.get('session_id')}"
    if event.type == "step_start":
        return f"{event.payload.get('display_name')} が応答中…"
    if event.type == "step_done":
        return "応答完了"
    if event.type == "step_error":
        return "エラーが発生しました"
    if event.type == "loop_check":
        payload = event.payload
        if payload.get("result") == "exit":
            return "ループ終了"
        return f"反復 {payload.get('iteration')} 完了"
    if event.type == "session_done":
        return IDLE_STATUS
    return "実行中…"


def _idle_ui(session: WebSession) -> UIUpdate:
    return (
        session.renderer.copy_messages(),
        IDLE_STATUS,
        False,
        "メッセージを入力…",
        False,
    )


def _pending_ui(session: WebSession, kind: str, event: EngineEvent) -> UIUpdate:
    if kind == "await_text":
        name = event.payload.get("display_name", "human")
        return (
            session.renderer.copy_messages(),
            f"{name} として入力してください",
            False,
            f"{name} として発言…",
            False,
        )
    return (
        session.renderer.copy_messages(),
        "続行または終了を選んでください",
        True,
        "メッセージを入力…",
        False,
    )


def process_events(
    session: WebSession,
    generator: Iterator[EngineEvent],
    first_event: EngineEvent | None = None,
) -> Generator[UIUpdate, None, None]:
    event = first_event if first_event is not None else next(generator)
    while True:
        pending_kind = session.renderer.apply(event)
        if pending_kind:
            session.pending = PendingInteraction(pending_kind, event, generator)
            yield _pending_ui(session, pending_kind, event)
            return

        yield (
            session.renderer.copy_messages(),
            _status_from_event(event),
            False,
            "メッセージを入力…",
            False,
        )

        try:
            event = next(generator)
        except StopIteration:
            break

    yield _idle_ui(session)


def resume_after_reply(session: WebSession, reply: str) -> Generator[UIUpdate, None, None]:
    pending = session.pending
    if pending is None:
        return
    session.pending = None
    try:
        event = pending.generator.send(reply)
    except StopIteration:
        yield _idle_ui(session)
        return
    yield from process_events(session, pending.generator, first_event=event)


def run_user_message(
    session: WebSession,
    display_text: str,
    prompt_text: str,
    *,
    org_id: str,
    workflow_value: str,
    stream: bool,
    temperature: float,
    attachment_context: str = "",
    attachment_names: list[str] | None = None,
) -> Generator[UIUpdate, None, None]:
    session.ensure_engine(org_id, workflow_value, stream, temperature)
    assert session.engine is not None
    session.renderer.add_user(display_text)
    yield (
        session.renderer.copy_messages(),
        "実行中…",
        False,
        "メッセージを入力…",
        True,
    )

    generator = session.engine.run_turn(
        prompt_text,
        attachment_context=attachment_context,
        attachments=attachment_names,
        stream=stream,
        temperature=temperature,
    )
    yield from process_events(session, generator)


def handle_chat_submit(
    session: WebSession,
    user_text: str,
    *,
    org_id: str,
    workflow_value: str,
    stream: bool,
    temperature: float,
    files=None,
    upload_limits: dict[str, int] | None = None,
) -> Generator[UIUpdate, None, None] | UIUpdate:
    text = (user_text or "").strip()

    if session.pending is not None:
        if session.pending.kind == "await_choice":
            return (
                session.renderer.copy_messages(),
                "続行または終了ボタンを使ってください",
                True,
                "メッセージを入力…",
                False,
            )
        if not text:
            name = session.pending.event.payload.get("display_name", "human")
            return (
                session.renderer.copy_messages(),
                "発言を入力してください",
                False,
                f"{name} として発言…",
                False,
            )
        yield from resume_after_reply(session, text)
        return

    limits = upload_limits or {}
    try:
        prompt_text, display_text, attachment_context, attachment_names = (
            resolve_user_input_with_attachments(text, files, limits)
        )
    except StudioValidationError as exc:
        return (
            session.renderer.copy_messages(),
            exc.format_all(),
            False,
            "メッセージを入力…",
            False,
        )

    if not prompt_text:
        return (
            session.renderer.copy_messages(),
            "メッセージを入力してください",
            False,
            "メッセージを入力…",
            False,
        )

    yield from run_user_message(
        session,
        display_text,
        prompt_text,
        org_id=org_id,
        workflow_value=workflow_value,
        stream=stream,
        temperature=temperature,
        attachment_context=attachment_context,
        attachment_names=attachment_names or None,
    )


def handle_choice(
    session: WebSession,
    choice: str,
) -> Generator[UIUpdate, None, None] | UIUpdate:
    if session.pending is None or session.pending.kind != "await_choice":
        return (
            session.renderer.copy_messages(),
            "選択待ちではありません",
            False,
            "メッセージを入力…",
            False,
        )
    yield from resume_after_reply(session, choice)


def load_org_panel(root: Path, org_id: str, workflow_value: str) -> tuple[str, str]:
    try:
        ctx = load_session_context(org_id, root, workflow_id=workflow_value or None)
        return talents_markdown(ctx), ""
    except StudioValidationError as exc:
        return talents_markdown_from_error(org_id), exc.format_all()


def talents_markdown_from_error(org_id: str) -> str:
    return f"**参加人材**\n\n組織 `{org_id}` の読み込みに失敗しました（model_mapping 等を確認）。"
