"""Gradio「🔊 声」サブタブ（設定編集の中）。組織ごとの voice_mapping.json を、1 人ずつ編集・試聴・保存する。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import gradio as gr

from studio.config_store import load_config
from studio.voice import DEFAULT_BASE_URL, parse_voicevox_urls, variant_voice_entry
from studio.voice_mapping import (
    PREVIEW_TEXT,
    SpeakerStyle,
    build_entry,
    build_variant,
    fetch_speakers,
    preview_wav,
    read_voice_mapping_raw,
    save_voice_mapping,
    shared_speakers,
)
from studio.web_ui import list_organizations

VARIANT_ROWS = 3
INHERIT = ""  # variant の声が「基本と同じ」
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])
_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"], scale=0, min_width=80)


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


def overview_markdown(root: Path, org_id: str | None, mapping: dict[str, dict[str, Any]]) -> str:
    ids = org_talent_ids(root, org_id)
    if not ids:
        return "組織を選んでください。"
    lines = [
        "| 人材 | 声（キャラ） | speaker | 速さ | 高さ | 抑揚 | 役割別 |",
        "|---|---|---|---|---|---|---|",
    ]
    for talent_id in ids:
        entry = mapping.get(talent_id)
        name = f"{talent_name(root, talent_id)} (`{talent_id}`)"
        if entry is None:
            lines.append(f"| {name} | —（読み上げない） | | | | | |")
            continue
        variants = len(entry.get("variants") or [])
        lines.append(
            f"| {name} | {entry.get('label', '')} | {entry.get('speaker', '')} | {_fmt(entry.get('speed'))} | "
            f"{_fmt(entry.get('pitch'))} | {_fmt(entry.get('intonation'))} | {variants or ''} |"
        )
    shared = shared_speakers({tid: mapping[tid] for tid in ids if tid in mapping})
    for speaker, members in shared.items():
        lines.append("")
        lines.append(f"⚠️ speaker {speaker} が重なっています: {', '.join(members)}（聞き分けにくくなります）")
    return "\n".join(lines)


def _voice_choices(speakers: list[SpeakerStyle], *, inherit: bool = False) -> list[tuple[str, Any]]:
    choices: list[tuple[str, Any]] = [(s.display, s.speaker_id) for s in speakers]
    return [("（基本と同じ）", INHERIT), *choices] if inherit else choices


def field_updates(entry: dict[str, Any] | None, speakers: list[SpeakerStyle]) -> list[Any]:
    """選んだ人材の値を、編集欄の順（FIELD_NAMES）の更新にする。"""
    entry = entry or {}
    base = _voice_choices(speakers)
    updates: list[Any] = [
        entry != {},
        gr.update(choices=base, value=entry.get("speaker")),
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


def _character_label(speakers: list[SpeakerStyle], speaker: Any, previous: dict[str, Any] | None) -> str:
    """VOICEVOX のクレジット表記になるキャラ名。一覧に無い ID は、同じ speaker の元の label を引き継ぐ。"""
    for style in speakers:
        if style.speaker_id == int(speaker):
            return style.character
    if previous and previous.get("speaker") == int(speaker):
        return str(previous.get("label") or "")
    return ""


def entry_from_fields(
    values: tuple[Any, ...], speakers: list[SpeakerStyle], previous: dict[str, Any] | None
) -> dict[str, Any]:
    """編集欄（FIELD_NAMES の enabled を除く順）から、voice_mapping の 1 件を作る。"""
    speaker, speed, pitch, intonation, when_action, *rows = values
    if speaker in (None, ""):
        raise ValueError("声（speaker）を選んでください")
    old_variants = [v for v in (previous or {}).get("variants") or [] if isinstance(v, dict)]
    variants: list[dict[str, Any]] = []
    for index in range(VARIANT_ROWS):
        when, voice, v_speed, v_pitch, v_intonation = rows[index * 5 : index * 5 + 5]
        previous_variant = old_variants[index] if index < len(old_variants) else None
        use_voice = voice not in (None, INHERIT)
        variant = build_variant(
            when_action=when,
            label=_character_label(speakers, voice, previous_variant) if use_voice else "",
            speaker=voice if use_voice else None,
            speed=v_speed,
            pitch=v_pitch,
            intonation=v_intonation,
        )
        if variant is not None:
            variants.append(variant)
    variants += old_variants[VARIANT_ROWS:]  # 画面に出していない 4 件目以降は、そのまま残す
    return build_entry(
        speaker=speaker,
        label=_character_label(speakers, speaker, previous),
        speed=speed,
        pitch=pitch,
        intonation=intonation,
        when_action=when_action,
        variants=variants,
    )


def save_entry(
    root: Path,
    org_id: str,
    talent_id: str,
    mapping: dict[str, dict[str, Any]],
    enabled: bool,
    values: tuple[Any, ...],
    speakers: list[SpeakerStyle],
) -> dict[str, dict[str, Any]]:
    """1 人分を反映して書き込み、新しいマッピングを返す。誤りは ValueError。"""
    updated = dict(mapping)
    if enabled:
        updated[talent_id] = entry_from_fields(values, speakers, mapping.get(talent_id))
    else:
        updated.pop(talent_id, None)
    ordered = [tid for tid in org_talent_ids(root, org_id) if tid in updated]
    ordered += [tid for tid in updated if tid not in ordered]  # user など、組織の人材以外はそのまま
    result = {tid: updated[tid] for tid in ordered}
    save_voice_mapping(root, org_id, result)
    return result


def build_voice_mapping_subtab(root: Path, *, voicevox_url: str | None = None) -> None:
    def engine_urls() -> list[str]:
        return parse_voicevox_urls(voicevox_url or DEFAULT_BASE_URL)

    orgs = list_organizations(root)
    with gr.Tab("🔊 声") as voice_tab:
        gr.Markdown(
            "組織ごとの声（`organizations/<組織>/voice_mapping.json`）を、人材ごとに編集します。"
            " 声の一覧は、VOICEVOX の ENGINE から取ります。役割別（action に含まれる文字列）に、声・速さ・高さ・抑揚を切り替えられます。"
        )
        mapping_state = gr.State({})
        org_dd = gr.Dropdown(label="組織", choices=orgs, value=orgs[0] if orgs else None)
        overview_md = gr.Markdown("_このタブを開くと表示します_")
        talent_dd = gr.Dropdown(label="編集する人材", choices=[], value=None)
        enabled_cb = gr.Checkbox(label="読み上げる（外すと、この人材は読み上げません）", value=True)
        voice_dd = gr.Dropdown(label="声（キャラ / スタイル）", choices=[], value=None, allow_custom_value=True)
        with gr.Row():
            speed = gr.Number(label="速さ（0.5〜2.0。空欄で標準）", value=None)
            pitch = gr.Number(label="高さ（-0.15〜0.15。空欄で標準）", value=None)
            intonation = gr.Number(label="抑揚（0〜2.0。空欄で標準）", value=None)
        when_action = gr.Textbox(
            label="この文字列を action に含む step だけ読む（空欄なら、すべて読む）", value=""
        )
        variant_fields: list[Any] = []
        with gr.Accordion("役割（action）で声を切り替える", open=False):
            gr.Markdown(
                "action に、ここで指定した文字列が含まれる step では、基本の声に重ねて使います（上の行から順に、最初に合うもの）。"
                " 空欄の項目は、基本と同じです。"
            )
            for number in range(1, VARIANT_ROWS + 1):
                with gr.Row():
                    v_when = gr.Textbox(label=f"役割{number}: action に含む文字列", value="")
                    v_voice = gr.Dropdown(
                        label=f"役割{number}: 声", choices=[("（基本と同じ）", INHERIT)], value=INHERIT, allow_custom_value=True
                    )
                with gr.Row():
                    v_speed = gr.Number(label=f"役割{number}: 速さ", value=None)
                    v_pitch = gr.Number(label=f"役割{number}: 高さ", value=None)
                    v_intonation = gr.Number(label=f"役割{number}: 抑揚", value=None)
                variant_fields += [v_when, v_voice, v_speed, v_pitch, v_intonation]
        field_comps = [enabled_cb, voice_dd, speed, pitch, intonation, when_action, *variant_fields]
        value_comps = field_comps[1:]  # enabled を除く

        with gr.Row():
            preview_target = gr.Radio(
                label="試聴する声", choices=["基本", *[f"役割{n}" for n in range(1, VARIANT_ROWS + 1)]], value="基本"
            )
            preview_text = gr.Textbox(label="試聴する文", value=PREVIEW_TEXT)
        with gr.Row():
            preview_btn = gr.Button("▶ 試聴", **_SAVE_BTN)
            save_btn = gr.Button("この人材を保存", **_SAVE_BTN)
        audio = gr.Audio(label="試聴", type="filepath", interactive=False)
        message_md = gr.Markdown("")

        def load_org(org_id: str | None):
            mapping = read_voice_mapping_raw(root, org_id) if org_id else {}
            ids = org_talent_ids(root, org_id)
            first = ids[0] if ids else None
            speakers = fetch_speakers(engine_urls())
            note = "" if speakers else "⚠️ VOICEVOX の ENGINE に接続できないため、声の一覧を取れません（speaker の番号は、直接入力できます）"
            choices = [(f"{talent_name(root, tid)} ({tid})", tid) for tid in ids]
            return (
                mapping,
                overview_markdown(root, org_id, mapping),
                gr.update(choices=choices, value=first),
                *field_updates(mapping.get(first) if first else None, speakers),
                note,
            )

        def on_talent(talent_id: str | None, mapping: dict):
            return field_updates((mapping or {}).get(talent_id) if talent_id else None, fetch_speakers(engine_urls()))

        def on_save(org_id, talent_id, mapping, enabled, *values):
            if not org_id or not talent_id:
                return mapping, gr.update(), "⚠️ 組織と人材を選んでください"
            try:
                updated = save_entry(root, org_id, talent_id, mapping or {}, bool(enabled), values, fetch_speakers(engine_urls()))
            except (ValueError, OSError) as exc:
                return mapping, gr.update(), f"❌ 保存できません:\n\n{exc}"
            return updated, overview_markdown(root, org_id, updated), f"✅ `{talent_id}` を保存しました（次の読み上げから使います）"

        def on_preview(org_id, talent_id, mapping, target, text, *values):
            speakers = fetch_speakers(engine_urls())
            try:
                entry = entry_from_fields(values, speakers, (mapping or {}).get(talent_id))
            except ValueError as exc:
                return None, f"⚠️ {exc}"
            if target != "基本":
                index = int(target.removeprefix("役割")) - 1
                when = values[5 + index * 5]
                if not (when or "").strip():
                    return None, f"⚠️ {target} の「action に含む文字列」を入力してください"
                entry = variant_voice_entry(entry, when.strip())
            try:
                wav = preview_wav(entry, text, engine_urls())
            except OSError as exc:
                return None, f"❌ 試聴できません: {exc}"
            with tempfile.NamedTemporaryFile(prefix="voice_preview_", suffix=".wav", delete=False) as f:
                f.write(wav)
            return f.name, ""

        org_outputs = [mapping_state, overview_md, talent_dd, *field_comps, message_md]
        voice_tab.select(load_org, inputs=[org_dd], outputs=org_outputs)
        org_dd.change(load_org, inputs=[org_dd], outputs=org_outputs)
        talent_dd.change(on_talent, inputs=[talent_dd, mapping_state], outputs=field_comps)
        save_btn.click(
            on_save,
            inputs=[org_dd, talent_dd, mapping_state, enabled_cb, *value_comps],
            outputs=[mapping_state, overview_md, message_md],
        )
        preview_btn.click(
            on_preview,
            inputs=[org_dd, talent_dd, mapping_state, preview_target, preview_text, *value_comps],
            outputs=[audio, message_md],
        )
