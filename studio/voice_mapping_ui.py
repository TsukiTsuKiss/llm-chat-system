"""Gradio「🔊 声」サブタブ（設定編集の中）。人材の既定の声・組織ごとの上書き・役割の話し方を、1 人ずつ編集・試聴・保存する。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import gradio as gr

from studio.config_store import load_config
from studio.voice import (
    DEFAULT_BASE_URL,
    VOICE_ROLES_KEY,
    SILENT_ENGINE,
    load_voice_mapping,
    parse_voicevox_urls,
    talent_voice,
    variant_voice_entry,
    voice_statuses,
)
from studio.voice_mapping import (
    PREVIEW_TEXT,
    SCALE_RANGES,
    SpeakerStyle,
    build_entry,
    build_roles,
    build_talent_voice,
    build_variant,
    fetch_speakers,
    preview_wav,
    read_talent_voice,
    read_voice_mapping_raw,
    save_talent_voice,
    save_voice_mapping,
    shared_speakers,
    slot_choices,
)
from studio.web_ui import list_organizations

VARIANT_ROWS = 3
ROLE_ROWS = 4
INHERIT = ""  # 「人材の既定（基本）と同じ」
SILENT_CHOICE = SILENT_ENGINE  # 人材の既定の声の選択肢「（音なし）」
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])
_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"], scale=0, min_width=80)
NO_VOICE_NOTE = "声がありません。人材の既定の声か、この組織の上書きで、声（speaker）を選んでください"
# スピンボタン 1 回で範囲外にならない刻み（既定の 1 だと、高さは一気に範囲外）
_SCALE_STEPS = {"speed": 0.05, "pitch": 0.01, "intonation": 0.05}


def _scale_field(key: str, label: str) -> gr.Number:
    low, high = SCALE_RANGES[key]
    return gr.Number(label=label, value=None, minimum=low, maximum=high, step=_SCALE_STEPS[key])


def org_talent_ids(root: Path, org_id: str | None) -> list[str]:
    if not org_id:
        return []
    try:
        return [str(t) for t in load_config("organization", org_id, root).get("talent_ids") or []]
    except (OSError, ValueError, KeyError):
        return []


def talent_name(root: Path, talent_id: str) -> str:
    try:
        return str(load_config("talent", talent_id, root).get("name") or talent_id)
    except (OSError, ValueError, KeyError):
        return talent_id


def _fmt(value: Any) -> str:
    return "" if value is None else f"{value:g}"


def overview_markdown(root: Path, org_id: str | None) -> str:
    """組織の人材ごとの、実際に使う声（人材の既定に組織の上書きを重ねたもの）と、その出どころ。"""
    ids = org_talent_ids(root, org_id)
    if not ids or not org_id:
        return "組織を選んでください。"
    raw = read_voice_mapping_raw(root, org_id)
    effective = load_voice_mapping(root, org_id)
    statuses = voice_statuses(root, org_id)
    lines = [
        "| 人材 | 声（キャラ） | speaker | 速さ | 高さ | 抑揚 | 出どころ | 状態 | 特定の発言 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for talent_id in ids:
        name = f"{talent_name(root, talent_id)} (`{talent_id}`)"
        override = raw.get(talent_id) or {}
        entry = effective.get(talent_id)
        status = statuses[talent_id]
        if status.kind != "voice" or entry is None:
            lines.append(f"| {name} | | | | | | | {status.text} | |")
        else:
            source = "組織の上書き" if "speaker" in override else "人材の既定"
            variants = len(entry.get("variants") or [])
            lines.append(
                f"| {name} | {entry.get('label', '')} | {entry['speaker']} | {_fmt(entry.get('speed'))} | "
                f"{_fmt(entry.get('pitch'))} | {_fmt(entry.get('intonation'))} | {source} | 読む | {variants or ''} |"
            )
    roles = raw.get(VOICE_ROLES_KEY) or {}
    if isinstance(roles, dict) and roles:
        lines += ["", "**役割の話し方**: " + " / ".join(
            f"{slot}（" + "、".join(f"{key} {_fmt(value)}" for key, value in style.items()) + "）"
            for slot, style in roles.items()
            if isinstance(style, dict)
        )]
    for speaker, members in shared_speakers(effective).items():
        lines += ["", f"⚠️ speaker {speaker} が重なっています: {', '.join(members)}（聞き分けにくくなります）"]
    return "\n".join(lines)


def _voice_choices(speakers: list[SpeakerStyle], *, inherit: bool = False) -> list[tuple[str, Any]]:
    choices: list[tuple[str, Any]] = [(s.display, s.speaker_id) for s in speakers]
    return [("（人材の既定と同じ）", INHERIT), *choices] if inherit else choices


def base_updates(voice: dict[str, Any] | None, speakers: list[SpeakerStyle]) -> list[Any]:
    voice = voice or {}
    silent = voice.get("engine") == SILENT_ENGINE
    return [
        gr.update(
            choices=[("（音なし）", SILENT_CHOICE), *_voice_choices(speakers)],
            value=SILENT_CHOICE if silent else voice.get("speaker"),
        ),
        voice.get("speed"),
        voice.get("pitch"),
        voice.get("intonation"),
    ]


def org_updates(entry: dict[str, Any] | None, speakers: list[SpeakerStyle]) -> list[Any]:
    entry = entry or {}
    updates: list[Any] = [
        entry.get("read") is not False,
        gr.update(choices=_voice_choices(speakers, inherit=True), value=entry.get("speaker", INHERIT)),
        entry.get("speed"),
        entry.get("pitch"),
        entry.get("intonation"),
        entry.get("when_action") or "",
    ]
    variants = [v for v in entry.get("variants") or [] if isinstance(v, dict)]
    for index in range(VARIANT_ROWS):
        variant = variants[index] if index < len(variants) else {}
        updates += [
            variant.get("when_action") or "",
            gr.update(choices=_voice_choices(speakers, inherit=True), value=variant.get("speaker", INHERIT)),
            variant.get("speed"),
            variant.get("pitch"),
            variant.get("intonation"),
        ]
    return updates


def role_updates(roles: Any, slots: list[str]) -> list[Any]:
    items = [(slot, style) for slot, style in (roles or {}).items() if isinstance(style, dict)]
    updates: list[Any] = []
    for index in range(ROLE_ROWS):
        slot, style = items[index] if index < len(items) else ("", {})
        updates += [
            gr.update(choices=slots, value=slot or None),
            style.get("speed"),
            style.get("pitch"),
            style.get("intonation"),
        ]
    return updates


def _character_label(speakers: list[SpeakerStyle], speaker: Any, previous: dict[str, Any] | None) -> str:
    """VOICEVOX のクレジット表記になるキャラ名。一覧に無い ID は、同じ speaker の元の label を引き継ぐ。"""
    for style in speakers:
        if style.speaker_id == int(speaker):
            return style.character
    if previous and previous.get("speaker") == int(speaker):
        return str(previous.get("label") or "")
    return ""


def _chosen(voice: Any) -> bool:
    return voice not in (None, INHERIT)


def talent_voice_from_fields(
    values: tuple[Any, ...], speakers: list[SpeakerStyle], previous: dict[str, Any] | None
) -> dict[str, Any] | None:
    """人材の既定の編集欄（声, 速さ, 高さ, 抑揚）から voice を作る。声が空なら None（既定の声なし）、「音なし」なら engine: none。"""
    speaker, speed, pitch, intonation = values
    if speaker == SILENT_CHOICE:
        return {"engine": SILENT_ENGINE}
    if not _chosen(speaker):
        return None
    return build_talent_voice(
        speaker=speaker, label=_character_label(speakers, speaker, previous), speed=speed, pitch=pitch, intonation=intonation
    )


def override_from_fields(
    read: bool, values: tuple[Any, ...], speakers: list[SpeakerStyle], previous: dict[str, Any] | None
) -> dict[str, Any]:
    """組織の編集欄（声, 速さ, 高さ, 抑揚, when_action, 特定の発言 3 行）から、上書き 1 件を作る。空欄は書かない。"""
    speaker, speed, pitch, intonation, when_action, *rows = values
    old_variants = [v for v in (previous or {}).get("variants") or [] if isinstance(v, dict)]
    variants: list[dict[str, Any]] = []
    for index in range(VARIANT_ROWS):
        when, voice, v_speed, v_pitch, v_intonation = rows[index * 5 : index * 5 + 5]
        previous_variant = old_variants[index] if index < len(old_variants) else None
        variant = build_variant(
            when_action=when,
            label=_character_label(speakers, voice, previous_variant) if _chosen(voice) else "",
            speaker=voice if _chosen(voice) else None,
            speed=v_speed,
            pitch=v_pitch,
            intonation=v_intonation,
        )
        if variant is not None:
            variants.append(variant)
    variants += old_variants[VARIANT_ROWS:]  # 画面に出していない 4 件目以降は、そのまま残す
    return build_entry(
        speaker=speaker if _chosen(speaker) else None,
        label=_character_label(speakers, speaker, previous) if _chosen(speaker) else "",
        speed=speed,
        pitch=pitch,
        intonation=intonation,
        when_action=when_action,
        variants=variants,
        read=read,
    )


def save_override(
    root: Path,
    org_id: str,
    talent_id: str,
    mapping: dict[str, Any],
    read: bool,
    values: tuple[Any, ...],
    speakers: list[SpeakerStyle],
) -> dict[str, Any]:
    """この組織の上書き 1 人分を反映して書き込み、新しいマッピングを返す。誤りは ValueError。"""
    entry = override_from_fields(read, values, speakers, mapping.get(talent_id))
    if read and "speaker" not in entry and talent_voice(root, talent_id) is None:
        raise ValueError(NO_VOICE_NOTE)
    updated = dict(mapping)
    if entry:
        updated[talent_id] = entry
    else:
        updated.pop(talent_id, None)  # 上書きなし = 人材の既定どおり
    return _write_mapping(root, org_id, updated)


def save_roles(root: Path, org_id: str, mapping: dict[str, Any], rows: tuple[Any, ...]) -> dict[str, Any]:
    roles = build_roles([tuple(rows[i * 4 : i * 4 + 4]) for i in range(ROLE_ROWS)])
    updated = dict(mapping)
    if roles:
        updated[VOICE_ROLES_KEY] = roles
    else:
        updated.pop(VOICE_ROLES_KEY, None)
    return _write_mapping(root, org_id, updated)


def _write_mapping(root: Path, org_id: str, updated: dict[str, Any]) -> dict[str, Any]:
    ordered = [tid for tid in org_talent_ids(root, org_id) if tid in updated]
    ordered += [key for key in updated if key not in ordered]  # user・_roles など
    result = {key: updated[key] for key in ordered}
    save_voice_mapping(root, org_id, result)
    return result


def preview_entry(
    base_values: tuple[Any, ...],
    read: bool,
    org_values: tuple[Any, ...],
    speakers: list[SpeakerStyle],
    target: str,
    previous: dict[str, Any] | None,
    previous_voice: dict[str, Any] | None,
) -> dict[str, Any]:
    """試聴する声。target は「人材の既定」「この組織」「特定の発言 n」。声がなければ ValueError。"""
    voice = talent_voice_from_fields(base_values, speakers, previous_voice) or {}
    if voice.get("engine") == SILENT_ENGINE:
        voice = {}
    if target == "人材の既定":
        entry = dict(voice)
    else:
        override = override_from_fields(read, org_values, speakers, previous)
        entry = {**voice, **{key: value for key, value in override.items() if key != "read"}}
    entry.pop("engine", None)
    if "speaker" not in entry:
        raise ValueError(NO_VOICE_NOTE)
    if target.startswith("特定の発言"):
        index = int(target.removeprefix("特定の発言")) - 1
        when = (org_values[5 + index * 5] or "").strip()
        if not when:
            raise ValueError(f"{target} の「action に含む文字列」を入力してください")
        entry = variant_voice_entry(entry, when)
    return entry


def describe_voice(entry: dict[str, Any]) -> str:
    """試聴したのがどの声かを示す文（キャラ名と、speaker・速さなどの設定値）。"""
    parts = [f"speaker {entry.get('speaker')}"]
    for key, name in (("speed", "速さ"), ("pitch", "高さ"), ("intonation", "抑揚")):
        if entry.get(key) is not None:
            parts.append(f"{name} {_fmt(entry[key])}")
    detail = "、".join(parts)
    label = entry.get("label") or ""
    return f"{label}（{detail}）" if label else detail


def build_voice_mapping_subtab(root: Path, *, voicevox_url: str | None = None) -> None:
    def engine_urls() -> list[str]:
        return parse_voicevox_urls(voicevox_url or DEFAULT_BASE_URL)

    orgs = list_organizations(root)
    with gr.Tab("🔊 声") as voice_tab:
        gr.Markdown(
            "声は 3 つの層で決まります。**人材の既定の声**（全組織で共通）に、**この組織での設定**（組織だけ変えたいとき）を重ね、"
            "さらに**役割の話し方**（速さ・高さ・抑揚）と、**特定の発言**での切り替えを重ねます。声の一覧は VOICEVOX の ENGINE から取ります。"
        )
        mapping_state = gr.State({})
        org_dd = gr.Dropdown(label="組織", choices=orgs, value=orgs[0] if orgs else None)
        overview_md = gr.Markdown("_このタブを開くと表示します_")
        top_note = gr.Markdown("")
        talent_dd = gr.Dropdown(label="編集する人材", choices=[], value=None)
        preview_text = gr.Textbox(label="試聴する文", value=PREVIEW_TEXT)

        with gr.Group():
            gr.Markdown("#### 人材の既定の声（全組織で共通。`talents/<id>.json` の voice）")
            base_voice = gr.Dropdown(label="声（キャラ / スタイル）", choices=[], value=None, allow_custom_value=True)
            with gr.Row():
                base_speed = _scale_field("speed", "速さ（0.5〜2.0。空欄で標準）")
                base_pitch = _scale_field("pitch", "高さ（-0.15〜0.15。空欄で標準）")
                base_intonation = _scale_field("intonation", "抑揚（0〜2.0。空欄で標準）")
            with gr.Row():
                base_preview_btn = gr.Button("▶ 人材の既定を試聴", **_SAVE_BTN)
                base_save_btn = gr.Button("人材の既定を保存", **_SAVE_BTN)
            base_msg = gr.Markdown("")
            base_audio = gr.Audio(label="試聴（人材の既定）", type="filepath", interactive=False, autoplay=True)
        base_fields = [base_voice, base_speed, base_pitch, base_intonation]

        with gr.Group():
            gr.Markdown("#### この組織での設定（空欄は、人材の既定どおり）")
            org_read = gr.Checkbox(label="読み上げる（外すと、この組織ではこの人材を読み上げません）", value=True)
            org_voice = gr.Dropdown(
                label="声を変える（キャラ / スタイル）", choices=[], value=INHERIT, allow_custom_value=True
            )
            with gr.Row():
                org_speed = _scale_field("speed", "速さ")
                org_pitch = _scale_field("pitch", "高さ")
                org_intonation = _scale_field("intonation", "抑揚")
            org_when = gr.Textbox(label="この文字列を action に含む step だけ読む（空欄なら、すべて読む）", value="")
            variant_fields: list[Any] = []
            with gr.Accordion("特定の発言（action）で声を切り替える", open=False):
                gr.Markdown(
                    "action に、ここで指定した文字列が含まれる step では、上の声に重ねて使います（上の行から順に、最初に合うもの）。"
                    " 空欄の項目は、上の声と同じです。"
                )
                for number in range(1, VARIANT_ROWS + 1):
                    with gr.Row():
                        v_when = gr.Textbox(label=f"発言{number}: action に含む文字列", value="")
                        v_voice = gr.Dropdown(
                            label=f"発言{number}: 声", choices=[("（人材の既定と同じ）", INHERIT)], value=INHERIT, allow_custom_value=True
                        )
                    with gr.Row():
                        v_speed = _scale_field("speed", f"発言{number}: 速さ")
                        v_pitch = _scale_field("pitch", f"発言{number}: 高さ")
                        v_intonation = _scale_field("intonation", f"発言{number}: 抑揚")
                    variant_fields += [v_when, v_voice, v_speed, v_pitch, v_intonation]
            preview_target = gr.Radio(
                label="試聴する声（この組織）",
                choices=["この組織", *[f"特定の発言{n}" for n in range(1, VARIANT_ROWS + 1)]],
                value="この組織",
            )
            with gr.Row():
                org_preview_btn = gr.Button("▶ この組織の声を試聴", **_SAVE_BTN)
                org_save_btn = gr.Button("この組織の設定を保存", **_SAVE_BTN)
            org_msg = gr.Markdown("")
            org_audio = gr.Audio(label="試聴（この組織）", type="filepath", interactive=False, autoplay=True)
        org_fields = [org_read, org_voice, org_speed, org_pitch, org_intonation, org_when, *variant_fields]

        with gr.Group():
            gr.Markdown(
                "#### 役割の話し方（この組織。`voice_mapping.json` の `_roles`）\n"
                "ワークフローの役割（スロット）ごとに、速さ・高さ・抑揚を変えます。その役割で話す人材すべてに効きます（声は変わりません）。"
            )
            role_fields: list[Any] = []
            for number in range(1, ROLE_ROWS + 1):
                with gr.Row():
                    r_name = gr.Dropdown(label=f"役割{number}", choices=[], value=None, allow_custom_value=True)
                    r_speed = _scale_field("speed", "速さ")
                    r_pitch = _scale_field("pitch", "高さ")
                    r_intonation = _scale_field("intonation", "抑揚")
                role_fields += [r_name, r_speed, r_pitch, r_intonation]
            roles_save_btn = gr.Button("役割の話し方を保存", **_SAVE_BTN)
            roles_msg = gr.Markdown("")

        def play(entry: dict[str, Any], text: str, who: str):
            try:
                wav = preview_wav(entry, text, engine_urls())
            except OSError as exc:
                return None, f"❌ 試聴できません: {exc}"
            with tempfile.NamedTemporaryFile(prefix="voice_preview_", suffix=".wav", delete=False) as f:
                f.write(wav)
            return f.name, f"🔊 試聴: {who} / {describe_voice(entry)}"

        def load_org(org_id: str | None):
            mapping = read_voice_mapping_raw(root, org_id) if org_id else {}
            ids = org_talent_ids(root, org_id)
            first = ids[0] if ids else None
            speakers = fetch_speakers(engine_urls())
            note = "" if speakers else "⚠️ VOICEVOX の ENGINE に接続できないため、声の一覧を取れません（speaker の番号は、直接入力できます）"
            choices = [(f"{talent_name(root, tid)} ({tid})", tid) for tid in ids]
            return (
                mapping,
                overview_markdown(root, org_id),
                gr.update(choices=choices, value=first),
                *base_updates(read_talent_voice(root, first) if first else None, speakers),
                *org_updates(mapping.get(first) if first else None, speakers),
                *role_updates(mapping.get(VOICE_ROLES_KEY), slot_choices(root)),
                note,
            )

        def on_talent(talent_id: str | None, mapping: dict):
            speakers = fetch_speakers(engine_urls())
            return (
                *base_updates(read_talent_voice(root, talent_id) if talent_id else None, speakers),
                *org_updates((mapping or {}).get(talent_id) if talent_id else None, speakers),
                None,  # 前の人の試聴とメッセージは消す
                None,
                "",
                "",
            )

        def on_save_base(org_id, talent_id, *base_values):
            if not talent_id:
                return gr.update(), "⚠️ 人材を選んでください"
            speakers = fetch_speakers(engine_urls())
            try:
                voice = talent_voice_from_fields(base_values, speakers, read_talent_voice(root, talent_id))
                save_talent_voice(root, talent_id, voice)
            except (ValueError, OSError) as exc:
                return gr.update(), f"❌ 保存できません:\n\n{exc}"
            message = (
                f"✅ `{talent_id}` の既定の声を保存しました（全組織に効きます）"
                if voice
                else f"✅ `{talent_id}` の既定の声を削除しました"
            )
            return overview_markdown(root, org_id), message

        def on_save_org(org_id, talent_id, mapping, read, *values):
            if not org_id or not talent_id:
                return mapping, gr.update(), "⚠️ 組織と人材を選んでください"
            try:
                updated = save_override(root, org_id, talent_id, mapping or {}, bool(read), values, fetch_speakers(engine_urls()))
            except (ValueError, OSError) as exc:
                return mapping, gr.update(), f"❌ 保存できません:\n\n{exc}"
            return updated, overview_markdown(root, org_id), f"✅ `{talent_id}` の組織の設定を保存しました（次の読み上げから使います）"

        def on_save_roles(org_id, mapping, *rows):
            if not org_id:
                return mapping, gr.update(), "⚠️ 組織を選んでください"
            try:
                updated = save_roles(root, org_id, mapping or {}, rows)
            except (ValueError, OSError) as exc:
                return mapping, gr.update(), f"❌ 保存できません:\n\n{exc}"
            return updated, overview_markdown(root, org_id), "✅ 役割の話し方を保存しました（次の読み上げから使います）"

        def on_preview(talent_id, mapping, target, text, org_read_value, *values):
            base_values, org_values = values[:4], values[4:]
            speakers = fetch_speakers(engine_urls())
            try:
                entry = preview_entry(
                    tuple(base_values),
                    bool(org_read_value),
                    tuple(org_values),
                    speakers,
                    target,
                    (mapping or {}).get(talent_id),
                    read_talent_voice(root, talent_id) if talent_id else None,
                )
            except ValueError as exc:
                return None, f"⚠️ {exc}"
            return play(entry, text, talent_name(root, talent_id) if talent_id else "")

        org_outputs = [mapping_state, overview_md, talent_dd, *base_fields, *org_fields, *role_fields, top_note]
        voice_tab.select(load_org, inputs=[org_dd], outputs=org_outputs)
        org_dd.change(load_org, inputs=[org_dd], outputs=org_outputs)
        talent_dd.change(
            on_talent,
            inputs=[talent_dd, mapping_state],
            outputs=[*base_fields, *org_fields, base_audio, org_audio, base_msg, org_msg],
        )
        base_save_btn.click(on_save_base, inputs=[org_dd, talent_dd, *base_fields], outputs=[overview_md, base_msg])
        org_save_btn.click(
            on_save_org,
            inputs=[org_dd, talent_dd, mapping_state, *org_fields],
            outputs=[mapping_state, overview_md, org_msg],
        )
        roles_save_btn.click(
            on_save_roles, inputs=[org_dd, mapping_state, *role_fields], outputs=[mapping_state, overview_md, roles_msg]
        )
        base_preview_btn.click(
            lambda talent_id, mapping, text, *values: on_preview(talent_id, mapping, "人材の既定", text, True, *values, *[None] * 20),
            inputs=[talent_dd, mapping_state, preview_text, *base_fields],
            outputs=[base_audio, base_msg],
        )
        org_preview_btn.click(
            on_preview,
            inputs=[talent_dd, mapping_state, preview_target, preview_text, org_read, *base_fields, *org_fields[1:]],
            outputs=[org_audio, org_msg],
        )
