"""Gradio chat display helpers for MultiRoleStudioWeb (design.md §6.3, §8.3)."""

from __future__ import annotations

import sys
import threading
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Generator, Iterator

import gradio as gr

from studio.assistants import MockAssistant
from studio.display import format_session_end_lines, format_step_metrics_line, SPEAKER_EMOJIS
from studio.engine import EngineEvent, SessionEngine
from studio.loader import SessionContext, load_session_context, read_attachment_files
from studio.rag_ui import last_injection_markdown
from studio.validation import StudioValidationError
from studio.voice import (
    DEFAULT_BASE_URL,
    AudioRelay,
    VoiceReader,
    engine_available,
    engine_monitor,
    load_voice_dictionary,
    load_voice_mapping,
    load_wav_array,
    parse_voicevox_urls,
)
from studio.voice_regen import missing_audio_files, regenerate_audio
from studio.voice_timeline import live_iframe_html, replay_iframe_html
from web_input_utils import normalize_uploaded_files

DIRECT_WORKFLOW_LABEL = "直接送信（全ロール）"
DIRECT_WORKFLOW_VALUE = ""
UNCONFIGURED_WORKFLOW_LABEL_SUFFIX = " — 未設定"

UIUpdate = tuple[list[dict[str, str]], str, bool, str, bool]

IDLE_STATUS = "待機中（メッセージを入力してください）"
FILE_ONLY_DEFAULT = "添付ファイルの内容を要約してください。"
VOICE_SWITCH_PATTERN = re.compile(
    r"(?:音声設定|読み上げ設定|読み上げ|音声)\s*(?:[:：=]\s*)?(on|off|オン|オフ|有効|無効|1|0)(?=\s|$)",
    re.IGNORECASE,
)


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


def workflow_available_for_org(root: Path, org_id: str, workflow_id: str | None) -> bool:
    if not org_id:
        return workflow_id in (None, "")
    try:
        load_session_context(org_id, root, workflow_id=workflow_id or None)
        return True
    except StudioValidationError:
        return False


def organizations_with_workflow(root: Path, workflow_id: str) -> list[str]:
    return [
        org_id
        for org_id in list_organizations(root)
        if workflow_available_for_org(root, org_id, workflow_id)
    ]


def workflow_unavailable_hint(root: Path, org_id: str, workflow_id: str) -> str:
    others = [
        oid for oid in organizations_with_workflow(root, workflow_id) if oid != org_id
    ]
    lines = [
        f"ワークフロー `{workflow_id}` は組織 `{org_id}` では未設定です。",
        "設定タブの `workflow_bindings` に追加してください。",
    ]
    if others:
        lines.append(f"設定済みの組織: {', '.join(f'`{o}`' for o in others)}")
    return "\n".join(lines)


def workflow_unavailable_note(root: Path, org_id: str, workflow_id: str) -> str:
    return f"**⚠️ ワークフロー未設定**\n\n{workflow_unavailable_hint(root, org_id, workflow_id)}"


def workflow_dropdown_choices_for_org(root: Path, org_id: str) -> list[tuple[str, str]]:
    """Chat tab: all workflows; unavailable ones are labeled but not executable."""
    choices: list[tuple[str, str]] = [(DIRECT_WORKFLOW_LABEL, DIRECT_WORKFLOW_VALUE)]
    for wf_id in list_workflows(root):
        if org_id and workflow_available_for_org(root, org_id, wf_id):
            choices.append((wf_id, wf_id))
        else:
            label = wf_id if not org_id else f"{wf_id}{UNCONFIGURED_WORKFLOW_LABEL_SUFFIX}"
            choices.append((label, wf_id))
    return choices


def resolve_workflow_value_for_org(
    root: Path,
    org_id: str,
    current_value: str | None = None,
) -> str:
    normalized = current_value or ""
    if normalized:
        if workflow_available_for_org(root, org_id, normalized):
            return normalized
    elif workflow_available_for_org(root, org_id, None):
        return DIRECT_WORKFLOW_VALUE

    default_wf = _org_default_workflow(root, org_id)
    if default_wf and workflow_available_for_org(root, org_id, default_wf):
        return default_wf
    return DIRECT_WORKFLOW_VALUE


def _org_default_workflow(root: Path, org_id: str) -> str:
    if not org_id:
        return ""
    try:
        from studio.config_store import load_config

        org = load_config("organization", org_id, root)
        return str(org.get("default_workflow") or "").strip()
    except (ValueError, OSError, KeyError):
        return ""


def initial_workflow_for_org(root: Path, org_id: str, requested: str | None = None) -> str:
    """起動時の選択。指定（--workflow）→ 組織の default_workflow → 直接送信 の順。"""
    for candidate in (requested, _org_default_workflow(root, org_id)):
        if candidate and workflow_available_for_org(root, org_id, candidate):
            return candidate
    return DIRECT_WORKFLOW_VALUE


def workflow_dropdown_for_org(
    root: Path,
    org_id: str,
    current_value: str | None = None,
) -> tuple[list[tuple[str, str]], str]:
    choices = workflow_dropdown_choices_for_org(root, org_id)
    value = resolve_workflow_value_for_org(root, org_id, current_value)
    allowed = {item_value for _, item_value in choices}
    if value not in allowed:
        value = DIRECT_WORKFLOW_VALUE
    return choices, value


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
    _active_placeholder: str = ""
    _last_display_name: dict[str, str] = field(default_factory=dict)
    last_done_idx: int | None = None

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
        self._active_placeholder = placeholder

    def _append_active(self, text: str) -> None:
        if self._active_idx is None:
            return
        content = self.messages[self._active_idx]["content"]
        if self._active_placeholder:
            content = content.removesuffix(self._active_placeholder)
            self._active_placeholder = ""
        self.messages[self._active_idx]["content"] = content + text

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
            self.last_done_idx = self._active_idx
        else:
            self.messages.append({"role": "assistant", "content": f"{header}\n\n{text}{footer}"})
            self.last_done_idx = len(self.messages) - 1
        self._active_idx = None

    def _add_system_note(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": f"_{text}_"})

    def add_note(self, text: str) -> None:
        self._add_system_note(text)

    def apply(self, event: EngineEvent) -> str | None:
        if event.type == "session_start":
            payload = event.payload
            wf = payload.get("workflow") or DIRECT_WORKFLOW_LABEL
            resumed = payload.get("resumed_from")
            branch = f"（`{resumed}` から再開）" if resumed else ""
            self._add_system_note(
                f"セッション開始 `{payload.get('session_id')}` — "
                f"{payload.get('org')} / {wf}{branch}"
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
            if payload.get("interrupt"):
                speaker = payload.get("prior_speaker", "AI")
                prior = payload.get("prior_text", "")
                hint = f"**{speaker}** からの質問に答えてください。"
                if prior:
                    hint = f"{hint}\n\n--- 直前の発言 ---\n{prior}"
                self._add_system_note(hint)
                return "await_text"
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
    user_context: bool = True
    user_context_rag: bool = True
    engine: SessionEngine | None = None
    pending: PendingInteraction | None = None
    renderer: ChatEventRenderer = field(default_factory=ChatEventRenderer)
    voicevox_url: str = DEFAULT_BASE_URL
    # スレッドを持つため gr.State の deepcopy 後に遅延生成する
    voice: VoiceReader | None = None
    relay: AudioRelay | None = None
    voice_enabled: bool = False
    # None: UI チェックボックス準拠 / True: 読み上げ許可 / False: 読み上げ停止
    director_voice_override: bool | None = None
    published_playing: int | None = None
    playing_seq: int = 0
    published_timing: str = ""
    # 再開したセッションの ID。タイミング記録があれば、チャット画面で再生できる
    replay_session_id: str = ""

    def live_chart_shown(self) -> bool:
        return bool(self.published_timing) and not self.published_timing.startswith("replay:")
    def close_voice(self) -> None:
        if self.voice is not None:
            self.voice.close(wait=False)
        self.voice = None
        self.voice_enabled = False
        if self.relay is not None:
            self.relay.clear()

    def configure_voice(self, enabled: bool) -> str:
        """読み上げを有効化。できないときは理由を返す（一部の ENGINE を外したときは通知を返して有効のまま）。"""
        self.voice_enabled = False
        if not enabled:
            return ""
        note = ""
        if self.voice is None:
            mapping = load_voice_mapping(self.root, self.org_id)
            if not mapping:
                return f"organizations/{self.org_id}/voice_mapping.json がないため読み上げません"
            configured = parse_voicevox_urls(self.voicevox_url)
            urls = [url for url in configured if engine_available(url)]
            if not urls:
                return f"VOICEVOX ({self.voicevox_url}) に接続できないため読み上げません"
            skipped = [url for url in configured if url not in urls]
            if skipped:
                note = f"接続できない VOICEVOX を外しました: {', '.join(skipped)}"
            self.relay = self.relay or AudioRelay()
            self.voice = VoiceReader(
                self.root,
                mapping,
                base_url=urls,
                play=False,
                dictionary=load_voice_dictionary(self.root, self.org_id),
                on_utterance=self._push_utterance,
                monitor=engine_monitor(configured),
                standby=skipped,
            )
            state = self.engine.state if self.engine is not None else None
            self.relay.timeline = self.voice.timeline
            if state is not None and state.logger is not None:
                self.voice.begin_session(state.logger.session_id)
        self.voice_enabled = self.director_voice_override is not False
        if self.director_voice_override is False:
            return (note + "\n" if note else "") + "ディレクター設定により読み上げ停止中です"
        return note

    def _is_director_talent(self, talent_id: str) -> bool:
        if self.engine is None or self.engine.ctx is None:
            return False
        bindings = self.engine.ctx.slot_bindings or {}
        return talent_id in (bindings.get("director") or [])

    def _extract_voice_switch(self, text: str) -> bool | None:
        normalized = unicodedata.normalize("NFKC", text or "")
        m = VOICE_SWITCH_PATTERN.search(normalized)
        if not m:
            return None
        token = m.group(1).lower()
        if token in ("on", "オン", "有効", "1"):
            return True
        if token in ("off", "オフ", "無効", "0"):
            return False
        return None

    def _apply_director_voice_switch(self, event: EngineEvent) -> None:
        if event.type != "step_done":
            return
        talent_id = event.payload.get("talent_id", "")
        if not talent_id or not self._is_director_talent(talent_id):
            return
        text = event.payload.get("text", "")
        switch = self._extract_voice_switch(text)
        if switch is None:
            normalized = unicodedata.normalize("NFKC", text)
            if "音声設定" in normalized or "読み上げ設定" in normalized:
                self.renderer.add_note(
                    "音声設定コマンドを解釈できませんでした（例: 音声設定: ON / 音声設定: OFF）"
                )
            return
        self.director_voice_override = switch
        self.voice_enabled = bool(switch and self.voice is not None)
        state_text = "ON" if switch else "OFF"
        self.renderer.add_note(f"ディレクター指示で読み上げを {state_text} に切替えました")

    def _push_utterance(self, path: Path) -> None:
        voice, relay = self.voice, self.relay
        if relay is not None:
            relay.push(path, voice.tags.pop(path, None) if voice is not None else None)

    def feed_voice(self, event: EngineEvent) -> None:
        self._apply_director_voice_switch(event)
        if self.voice_enabled and self.voice is not None:
            tag = self.renderer.last_done_idx if event.type == "step_done" else None
            self.voice.handle(event, tag)

    def mark_turn_end(self) -> None:
        if self.voice_enabled and self.voice is not None:
            self.voice.timeline.add("turn_end")

    def close_engine(self) -> str:
        if self.engine is None or self.engine.state is None or not self.engine.state.started:
            return ""
        end_event = self.engine.finish()
        lines = format_session_end_lines(end_event.payload)
        return "\n".join(line.strip() for line in lines if line.strip())

    def reset_chat(self) -> str:
        summary = self.close_engine()
        self.close_voice()
        self.director_voice_override = None
        self.replay_session_id = ""
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

    def resume_branch(
        self,
        resumed,
        ctx: SessionContext,
        *,
        stream: bool,
        temperature: float,
        user_context: bool = True,
        user_context_rag: bool = True,
    ) -> None:
        import time

        from studio.engine import EngineState, SessionEngine
        from studio.session_resume import ResumedSession
        from studio.user_context import resolve_user_context
        from studio.user_context_rag import session_rag_enabled

        if not isinstance(resumed, ResumedSession):
            raise TypeError("resumed must be ResumedSession")
        uc_resolution = resolve_user_context(
            ctx.root,
            ctx.studio_config,
            no_user_context=not user_context,
        )
        rag_enabled = session_rag_enabled(
            ctx.studio_config,
            no_user_context=not user_context,
            no_user_context_rag=not user_context_rag,
        )
        self.user_context_rag = user_context_rag
        self.reset_chat()
        self.org_id = resumed.org_id
        self.workflow_id = resumed.workflow_id
        self.stream = stream
        self.temperature = temperature
        self.renderer = ChatEventRenderer()
        self.renderer.messages = list(resumed.replay_messages)
        self.renderer.messages.append(
            {
                "role": "assistant",
                "content": (
                    f"_再開 `{resumed.parent_session_id}` から。"
                    " 続きを入力してください。_"
                ),
            }
        )
        self.engine = SessionEngine(ctx)
        self.engine.state = EngineState(
            ctx=ctx,
            logger=None,
            histories=resumed.histories,
            step_number=resumed.step_number,
            stream=stream,
            temperature=temperature,
            user_context_enabled=uc_resolution.enabled,
            user_context_text=uc_resolution.text,
            user_context_rag_enabled=rag_enabled,
            parent_session_id=resumed.parent_session_id,
            session_wall_start=time.perf_counter(),
        )


def _regenerate_quietly(root: Path, session_id: str, urls: list[str]) -> None:
    try:
        regenerate_audio(root, session_id, urls=urls)
    except Exception as exc:
        print(f"[voice] 音声の再生成に失敗しました: {exc}", file=sys.stderr)


def apply_session_resume(
    web: WebSession,
    session_id: str,
    *,
    stream: bool,
    temperature: float,
    user_context: bool = True,
    user_context_rag: bool = True,
) -> tuple[
    WebSession,
    list[dict[str, str]],
    str,
    str,
    dict,
    dict,
    str,
    str,
    str,
    str,
]:
    from studio.session_resume import load_resumed_session

    resumed = load_resumed_session(web.root, session_id)
    workflow_value = resumed.workflow_id or ""
    ctx = load_session_context(resumed.org_id, web.root, workflow_id=resumed.workflow_id)
    MockAssistant.reset()
    web.resume_branch(
        resumed,
        ctx,
        stream=stream,
        temperature=temperature,
        user_context=user_context,
        user_context_rag=user_context_rag,
    )
    web.replay_session_id = session_id
    missing = missing_audio_files(web.root, session_id)
    if missing:
        threading.Thread(
            target=_regenerate_quietly,
            args=(web.root, session_id, parse_voicevox_urls(web.voicevox_url)),
            daemon=True,
        ).start()
    choices, wf_value = workflow_dropdown_for_org(web.root, resumed.org_id, workflow_value)
    talents = load_org_panel(web.root, resumed.org_id, wf_value)[0]
    status = (
        f"再開 `{resumed.parent_session_id}` — "
        "メッセージを送ると分岐セッションを開始します"
    )
    msg = (
        f"**再開** — `{resumed.parent_session_id}` をチャットタブに読み込みました。"
        " 続きを入力してください。"
    )
    if missing:
        msg += f" 音声が無い発言 {len(missing)} 件を、バックグラウンドで再生成します。"
    return (
        web,
        web.renderer.copy_messages(),
        status,
        resumed.org_id,
        gr.update(value=resumed.org_id),
        gr.update(choices=choices, value=wf_value),
        talents,
        wf_value,
        "",
        msg,
    )


def _status_from_event(event: EngineEvent) -> str:
    if event.type == "session_start":
        return f"セッション {event.payload.get('session_id')}"
    if event.type == "step_start":
        return f"{event.payload.get('display_name')} が応答中…"
    if event.type == "chunk":
        return "応答を出力中…"
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
        if event.payload.get("interrupt"):
            return (
                session.renderer.copy_messages(),
                "質問に答えてください",
                False,
                "回答を入力…",
                False,
            )
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
        session.feed_voice(event)
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

    session.mark_turn_end()
    yield _idle_ui(session)


def resume_after_reply(session: WebSession, reply: str) -> Generator[UIUpdate, None, None]:
    pending = session.pending
    if pending is None:
        return
    session.pending = None
    try:
        event = pending.generator.send(reply)
    except StopIteration:
        session.mark_turn_end()
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
    user_context: bool = True,
    user_context_rag: bool = True,
    attachment_context: str = "",
    attachment_names: list[str] | None = None,
    web_search: bool = False,
    voice: bool = False,
) -> Generator[UIUpdate, None, None]:
    session.ensure_engine(org_id, workflow_value, stream, temperature)
    voice_note = session.configure_voice(voice)
    if voice_note:
        session.renderer.add_note(f"⚠️ {voice_note}")
    session.stream = stream
    session.temperature = temperature
    session.user_context = user_context
    session.user_context_rag = user_context_rag
    assert session.engine is not None
    try:
        from studio.loader import load_studio_config

        session.engine.ctx.studio_config = load_studio_config(session.root)
    except StudioValidationError:
        pass
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
        no_user_context=not user_context,
        no_user_context_rag=not user_context_rag,
        web_search=web_search,
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
    user_context: bool = True,
    user_context_rag: bool = True,
    files=None,
    upload_limits: dict[str, int] | None = None,
    web_search: bool = False,
    voice: bool = False,
) -> Generator[UIUpdate, None, None] | UIUpdate:
    text = (user_text or "").strip()

    if session.pending is not None:
        if session.pending.kind == "await_choice":
            yield (
                session.renderer.copy_messages(),
                "続行または終了ボタンを使ってください",
                True,
                "メッセージを入力…",
                False,
            )
            return
        if not text:
            name = session.pending.event.payload.get("display_name", "human")
            yield (
                session.renderer.copy_messages(),
                "発言を入力してください",
                False,
                f"{name} として発言…",
                False,
            )
            return
        session.renderer.add_user(text)
        yield (
            session.renderer.copy_messages(),
            "実行中…",
            False,
            "メッセージを入力…",
            True,
        )
        yield from resume_after_reply(session, text)
        return

    limits = upload_limits or {}
    try:
        prompt_text, display_text, attachment_context, attachment_names = (
            resolve_user_input_with_attachments(text, files, limits)
        )
    except StudioValidationError as exc:
        yield (
            session.renderer.copy_messages(),
            exc.format_all(),
            False,
            "メッセージを入力…",
            False,
        )
        return

    if not prompt_text:
        yield (
            session.renderer.copy_messages(),
            "メッセージを入力してください",
            False,
            "メッセージを入力…",
            False,
        )
        return

    yield from run_user_message(
        session,
        display_text,
        prompt_text,
        org_id=org_id,
        workflow_value=workflow_value,
        stream=stream,
        temperature=temperature,
        user_context=user_context,
        user_context_rag=user_context_rag,
        attachment_context=attachment_context,
        attachment_names=attachment_names or None,
        web_search=web_search,
        voice=voice,
    )


_LED_COLORS = {"off": "#555555", "idle": "#2ecc40", "busy": "#ff4136"}
_LED_LABELS = {"off": "未検出", "idle": "待機", "busy": "合成中"}


def engine_led_html(states: list[tuple[str, str]]) -> str:
    """ENGINE ごとの LED（消灯=未検出 / 緑=待機 / 赤=合成中）。ホバーで URL と状態を表示する。"""
    if not states:
        return ""
    leds = "".join(
        f'<span title="{escape(url)}: {_LED_LABELS[state]}" style="display:inline-block;width:14px;height:14px;'
        f"border-radius:50%;margin-right:6px;background:{_LED_COLORS[state]};"
        f'box-shadow:{"none" if state == "off" else "0 0 6px " + _LED_COLORS[state]}"></span>'
        for url, state in states
    )
    return f'<div style="display:flex;align-items:center;gap:4px">VOICEVOX&nbsp;{leds}</div>'


def _playing_update(session: WebSession):
    """再生中の発言番号が変わったときだけ、隠し Textbox へ送る値を返す。"""
    playing = session.relay.playing_tag if session.relay is not None else None
    if playing == session.published_playing:
        return gr.skip()
    session.published_playing = playing
    session.playing_seq += 1
    # 同じ発言番号を続けて送っても change が発火するよう、連番を付ける
    return f"{session.playing_seq}:{'' if playing is None else playing}"


def live_timing_update(session: WebSession, show: bool = True):
    """送信ボタン下のチャート。読み上げ中はライブ、再開したセッションに記録があれば再生を出す。show=False で隠す。"""
    timeline = session.voice.timeline if session.voice is not None and session.voice_enabled else None
    key = (timeline.session_id or "") if timeline is not None else ""
    replay_id = session.replay_session_id
    if not key and replay_id and (session.root / "sessions" / "audio" / replay_id / "timeline.jsonl").is_file():
        key = f"replay:{replay_id}"
    if not show:
        key = ""
    if key == session.published_timing:
        return gr.skip()
    session.published_timing = key
    if not key:
        return gr.update(value="", visible=False)
    if key.startswith("replay:"):
        try:
            return gr.update(value=replay_iframe_html(session.root, replay_id, compact=True), visible=True)
        except FileNotFoundError:
            return gr.update(value="", visible=False)
    if timeline is None or timeline.out_dir is None:
        return gr.update(value="", visible=False)
    return gr.update(value=live_iframe_html(key, timeline.out_dir), visible=True)


def next_audio_update(session: WebSession):
    """(gr.Audio, 再生中の発言を知らせる隠し Textbox) の更新。チャット本文は書き換えない。変化がなければ gr.skip()。"""
    path = session.relay.next_if_idle() if session.relay is not None else None
    audio = load_wav_array(path) if path is not None else gr.skip()
    return audio, _playing_update(session)


def audio_started_update(session: WebSession):
    """ブラウザで再生が始まったとき。待ち時間の起点を再生開始に合わせる。"""
    if session.relay is not None:
        session.relay.started()
    return _playing_update(session)


def audio_finished_update(session: WebSession):
    if session.relay is not None:
        session.relay.finished()
    return next_audio_update(session)


def handle_choice(
    session: WebSession,
    choice: str,
) -> Generator[UIUpdate, None, None] | UIUpdate:
    if session.pending is None or session.pending.kind != "await_choice":
        yield (
            session.renderer.copy_messages(),
            "選択待ちではありません",
            False,
            "メッセージを入力…",
            False,
        )
        return
    yield from resume_after_reply(session, choice)


def last_rag_injection_preview(session: WebSession) -> str:
    if session.engine is None or session.engine.state is None:
        return last_injection_markdown(())
    return last_injection_markdown(session.engine.state.last_context_chunks)


def load_org_panel(root: Path, org_id: str, workflow_value: str) -> tuple[str, str]:
    try:
        ctx = load_session_context(org_id, root, workflow_id=workflow_value or None)
        return talents_markdown(ctx), ""
    except StudioValidationError as exc:
        detail = exc.format_all()
        return (
            f"**参加人材**\n\n"
            f"組織 `{org_id}` の読み込みに失敗しました。\n\n"
            f"```\n{detail}\n```",
            detail,
        )


def talents_markdown_from_error(org_id: str) -> str:
    return f"**参加人材**\n\n組織 `{org_id}` の読み込みに失敗しました。"
