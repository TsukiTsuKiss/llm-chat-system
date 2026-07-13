"""Gradio settings tab (design.md §8.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from studio.config_store import (
    create_organization,
    create_talent,
    create_workflow,
    delete_config,
    list_configs,
    load_config,
    mapping_to_json_text,
    parse_mapping_json,
    save_config,
)
from studio.web_ui import load_org_panel, workflow_dropdown_choices


@dataclass
class SettingsHandles:
    org_dd: gr.Dropdown
    wf_dd: gr.Dropdown
    talents_md: gr.Markdown


def _tags_to_str(tags: list[str] | None) -> str:
    return ", ".join(tags or [])


def _str_to_tags(text: str) -> list[str]:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def _lines_to_list(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _list_to_lines(items: list[str] | None) -> str:
    return "\n".join(items or [])


def build_settings_tab(root: Path, handles: SettingsHandles, demo: gr.Blocks) -> None:
    talent_ids = list_configs("talent", root)
    org_ids = list_configs("organization", root)
    wf_ids = list_configs("workflow", root)

    with gr.Tab("⚙️ 設定編集"):
        gr.Markdown("人材・組織・ワークフローを編集します。保存前にバリデーションを実行します（§8.4）。")

        with gr.Tabs():
            # --- Talent ---
            with gr.Tab("👤 人材"):
                with gr.Row():
                    talent_id_dd = gr.Dropdown(
                        label="人材 ID",
                        choices=talent_ids,
                        value=talent_ids[0] if talent_ids else None,
                        allow_custom_value=True,
                    )
                    talent_new_id = gr.Textbox(label="新規 ID", placeholder="例: my_bot")
                    talent_create_btn = gr.Button("新規作成", variant="secondary")
                    talent_delete_btn = gr.Button("削除", variant="stop")
                talent_name = gr.Textbox(label="name")
                talent_personality = gr.Textbox(label="personality", lines=2)
                talent_tags = gr.Textbox(label="tags（カンマ区切り）")
                talent_prompt = gr.Textbox(label="system_prompt", lines=10)
                talent_save_btn = gr.Button("保存", variant="primary")
                talent_msg = gr.Markdown("")

            # --- Organization ---
            with gr.Tab("🏢 組織"):
                with gr.Row():
                    org_id_dd = gr.Dropdown(
                        label="組織 ID",
                        choices=org_ids,
                        value=org_ids[0] if org_ids else None,
                        allow_custom_value=True,
                    )
                    org_new_id = gr.Textbox(label="新規組織 ID")
                    org_new_talent = gr.Dropdown(
                        label="初期人材（必須）",
                        choices=talent_ids,
                        value=talent_ids[0] if talent_ids else None,
                    )
                    org_create_btn = gr.Button("新規作成", variant="secondary")
                    org_delete_btn = gr.Button("削除", variant="stop")
                org_name = gr.Textbox(label="name")
                org_mission = gr.Textbox(label="mission", lines=2)
                org_culture = gr.Textbox(label="culture（1行1項目）", lines=4)
                org_talent_ids = gr.CheckboxGroup(
                    label="talent_ids",
                    choices=talent_ids,
                    value=talent_ids[:1] if talent_ids else [],
                )
                org_bindings_json = gr.Textbox(
                    label="workflow_bindings（JSON）",
                    lines=6,
                    placeholder='{"discussion": {"participant": ["solo_bot"]}}',
                )
                org_directives_json = gr.Textbox(
                    label="common_directives / role_directives（JSON）",
                    lines=6,
                    placeholder='{"common_directives": [], "role_directives": {}}',
                )
                org_default_wf = gr.Textbox(label="default_workflow（任意）")
                org_mapping_json = gr.Textbox(label="model_mapping.json", lines=10)
                org_save_btn = gr.Button("組織 config を保存", variant="primary")
                org_mapping_save_btn = gr.Button("model_mapping を保存", variant="primary")
                org_msg = gr.Markdown("")

            # --- Workflow ---
            with gr.Tab("🔄 ワークフロー"):
                with gr.Row():
                    wf_id_dd = gr.Dropdown(
                        label="ワークフロー ID",
                        choices=wf_ids,
                        value=wf_ids[0] if wf_ids else None,
                        allow_custom_value=True,
                    )
                    wf_new_id = gr.Textbox(label="新規 ID")
                    wf_create_btn = gr.Button("新規作成", variant="secondary")
                    wf_delete_btn = gr.Button("削除", variant="stop")
                wf_json = gr.Textbox(label="workflows/<id>.json", lines=24)
                wf_save_btn = gr.Button("保存", variant="primary")
                wf_msg = gr.Markdown("")

    def _refresh_talent_choices(current: str | None = None):
        ids = list_configs("talent", root)
        value = current if current in ids else (ids[0] if ids else None)
        return (
            gr.update(choices=ids, value=value),
            gr.update(choices=ids, value=value),
            gr.update(choices=ids),
            ids,
        )

    def load_talent(talent_id: str):
        data = load_config("talent", talent_id, root) if talent_id else {}
        return (
            data.get("name", ""),
            data.get("personality", ""),
            _tags_to_str(data.get("tags")),
            data.get("system_prompt", ""),
            "",
        )

    def save_talent(talent_id: str, name: str, personality: str, tags: str, prompt: str):
        data = {
            "name": name.strip(),
            "system_prompt": prompt.strip(),
        }
        if personality.strip():
            data["personality"] = personality.strip()
        tag_list = _str_to_tags(tags)
        if tag_list:
            data["tags"] = tag_list
        result = save_config("talent", talent_id, data, root)
        dd_upd, new_talent_upd, cb_upd, _ids = _refresh_talent_choices(talent_id if result.ok else None)
        return result.message, dd_upd, new_talent_upd, cb_upd

    def on_talent_create(new_id: str):
        result = create_talent(new_id, root)
        dd_upd, new_talent_upd, cb_upd, _ids = _refresh_talent_choices(new_id if result.ok else None)
        if result.ok:
            loaded = load_talent(new_id)
            return (result.message, dd_upd, new_talent_upd, cb_upd, *loaded)
        return (result.message, dd_upd, new_talent_upd, cb_upd, "", "", "", "", "")

    def on_talent_delete(talent_id: str):
        result = delete_config("talent", talent_id, root)
        dd_upd, new_talent_upd, cb_upd, _ids = _refresh_talent_choices()
        return result.message, dd_upd, new_talent_upd, cb_upd, "", "", "", "", ""

    talent_id_dd.change(
        load_talent,
        inputs=[talent_id_dd],
        outputs=[talent_name, talent_personality, talent_tags, talent_prompt, talent_msg],
    )
    talent_save_btn.click(
        save_talent,
        inputs=[talent_id_dd, talent_name, talent_personality, talent_tags, talent_prompt],
        outputs=[talent_msg, talent_id_dd, org_new_talent, org_talent_ids],
    )
    talent_create_btn.click(
        on_talent_create,
        inputs=[talent_new_id],
        outputs=[
            talent_msg,
            talent_id_dd,
            org_new_talent,
            org_talent_ids,
            talent_name,
            talent_personality,
            talent_tags,
            talent_prompt,
        ],
    )
    talent_delete_btn.click(
        on_talent_delete,
        inputs=[talent_id_dd],
        outputs=[
            talent_msg,
            talent_id_dd,
            org_new_talent,
            org_talent_ids,
            talent_name,
            talent_personality,
            talent_tags,
            talent_prompt,
        ],
    )

    def load_org(org_id: str):
        if not org_id:
            return "", "", "", [], "{}", "{}", "", "", ""
        data = load_config("organization", org_id, root)
        mapping = load_config("model_mapping", "", root, org_id=org_id)
        extra = {
            "common_directives": data.get("common_directives", []),
            "role_directives": data.get("role_directives", {}),
        }
        return (
            data.get("name", ""),
            data.get("mission", ""),
            _list_to_lines(data.get("culture")),
            data.get("talent_ids") or [],
            json.dumps(data.get("workflow_bindings") or {}, ensure_ascii=False, indent=2),
            json.dumps(extra, ensure_ascii=False, indent=2),
            data.get("default_workflow") or "",
            mapping_to_json_text(mapping),
            "",
        )

    def _build_org_config(
        name: str,
        mission: str,
        culture: str,
        talent_ids_selected: list[str],
        bindings_json: str,
        directives_json: str,
        default_wf: str,
    ) -> tuple[dict[str, Any] | None, str]:
        if not talent_ids_selected:
            return None, "talent_ids を1つ以上選択してください"
        config: dict[str, Any] = {"talent_ids": list(talent_ids_selected)}
        if name.strip():
            config["name"] = name.strip()
        if mission.strip():
            config["mission"] = mission.strip()
        culture_list = _lines_to_list(culture)
        if culture_list:
            config["culture"] = culture_list
        try:
            bindings = json.loads(bindings_json or "{}")
        except json.JSONDecodeError as exc:
            return None, f"workflow_bindings JSON エラー: {exc}"
        if bindings:
            config["workflow_bindings"] = bindings
        try:
            directives = json.loads(directives_json or "{}")
        except json.JSONDecodeError as exc:
            return None, f"directives JSON エラー: {exc}"
        if directives.get("common_directives"):
            config["common_directives"] = directives["common_directives"]
        if directives.get("role_directives"):
            config["role_directives"] = directives["role_directives"]
        if default_wf and str(default_wf).strip():
            config["default_workflow"] = str(default_wf).strip()
        return config, ""

    def save_org(org_id: str, *fields):
        config, err = _build_org_config(*fields)
        if config is None:
            return err, gr.update(), gr.update(), gr.update()
        result = save_config("organization", org_id, config, root)
        orgs = list_configs("organization", root)
        org_upd = gr.update(
            choices=orgs,
            value=org_id if result.ok and org_id in orgs else (orgs[0] if orgs else None),
        )
        wf_upd = gr.update(choices=workflow_dropdown_choices(root))
        talents_text = load_org_panel(root, org_id, "")[0] if result.ok else gr.update()
        return result.message, org_upd, wf_upd, talents_text

    org_fields = [
        org_name,
        org_mission,
        org_culture,
        org_talent_ids,
        org_bindings_json,
        org_directives_json,
        org_default_wf,
    ]
    org_save_btn.click(
        save_org,
        inputs=[org_id_dd, *org_fields],
        outputs=[org_msg, handles.org_dd, handles.wf_dd, handles.talents_md],
    )

    def save_org_mapping(org_id: str, mapping_text: str):
        mapping, err = parse_mapping_json(mapping_text)
        if mapping is None:
            return err, gr.update()
        result = save_config("model_mapping", "", mapping, root, org_id=org_id)
        talents_text = load_org_panel(root, org_id, "")[0] if result.ok else gr.update()
        return result.message, talents_text

    org_mapping_save_btn.click(
        save_org_mapping,
        inputs=[org_id_dd, org_mapping_json],
        outputs=[org_msg, handles.talents_md],
    )

    def on_org_create(new_id: str, initial_talent: str, name: str):
        result = create_organization(new_id, root, initial_talent_id=initial_talent, name=name)
        orgs = list_configs("organization", root)
        org_dd_upd = gr.update(
            choices=orgs,
            value=new_id if result.ok and new_id in orgs else (orgs[0] if orgs else None),
        )
        chat_org_upd = org_dd_upd
        wf_upd = gr.update(choices=workflow_dropdown_choices(root))
        if result.ok:
            loaded = load_org(new_id)
            return (result.message, org_dd_upd, chat_org_upd, wf_upd, *loaded)
        return (result.message, org_dd_upd, chat_org_upd, wf_upd, "", "", "", [], "{}", "{}", "", "", "")

    org_create_btn.click(
        on_org_create,
        inputs=[org_new_id, org_new_talent, org_name],
        outputs=[
            org_msg,
            org_id_dd,
            handles.org_dd,
            handles.wf_dd,
            org_name,
            org_mission,
            org_culture,
            org_talent_ids,
            org_bindings_json,
            org_directives_json,
            org_default_wf,
            org_mapping_json,
        ],
    )

    def on_org_delete(org_id: str):
        result = delete_config("organization", org_id, root)
        orgs = list_configs("organization", root)
        org_dd_upd = gr.update(choices=orgs, value=orgs[0] if orgs else None)
        chat_org_upd = org_dd_upd
        wf_upd = gr.update(choices=workflow_dropdown_choices(root))
        return result.message, org_dd_upd, chat_org_upd, wf_upd, "", "", "", [], "{}", "{}", "", "", ""

    org_delete_btn.click(
        on_org_delete,
        inputs=[org_id_dd],
        outputs=[
            org_msg,
            org_id_dd,
            handles.org_dd,
            handles.wf_dd,
            org_name,
            org_mission,
            org_culture,
            org_talent_ids,
            org_bindings_json,
            org_directives_json,
            org_default_wf,
            org_mapping_json,
        ],
    )

    org_id_dd.change(
        load_org,
        inputs=[org_id_dd],
        outputs=[
            org_name,
            org_mission,
            org_culture,
            org_talent_ids,
            org_bindings_json,
            org_directives_json,
            org_default_wf,
            org_mapping_json,
            org_msg,
        ],
    )

    def load_workflow(wf_id: str):
        if not wf_id:
            return "", ""
        data = load_config("workflow", wf_id, root)
        return json.dumps(data, ensure_ascii=False, indent=2), ""

    def save_workflow(wf_id: str, text: str):
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            return f"JSON 構文エラー: {exc}", gr.update()
        if not isinstance(data, dict):
            return "ワークフローは JSON オブジェクトである必要があります", gr.update()
        result = save_config("workflow", wf_id, data, root)
        wf_upd = gr.update(choices=workflow_dropdown_choices(root))
        return result.message, wf_upd

    wf_id_dd.change(load_workflow, inputs=[wf_id_dd], outputs=[wf_json, wf_msg])
    wf_save_btn.click(save_workflow, inputs=[wf_id_dd, wf_json], outputs=[wf_msg, handles.wf_dd])

    def on_wf_create(new_id: str):
        result = create_workflow(new_id, root)
        ids = list_configs("workflow", root)
        dd_upd = gr.update(choices=ids, value=new_id if result.ok else (ids[0] if ids else None))
        wf_chat_upd = gr.update(choices=workflow_dropdown_choices(root))
        if result.ok:
            return result.message, dd_upd, wf_chat_upd, load_workflow(new_id)[0]
        return result.message, dd_upd, wf_chat_upd, ""

    wf_create_btn.click(
        on_wf_create,
        inputs=[wf_new_id],
        outputs=[wf_msg, wf_id_dd, handles.wf_dd, wf_json],
    )

    def on_wf_delete(wf_id: str):
        result = delete_config("workflow", wf_id, root)
        ids = list_configs("workflow", root)
        dd_upd = gr.update(choices=ids, value=ids[0] if ids else None)
        wf_chat_upd = gr.update(choices=workflow_dropdown_choices(root))
        return result.message, dd_upd, wf_chat_upd, ""

    wf_delete_btn.click(
        on_wf_delete,
        inputs=[wf_id_dd],
        outputs=[wf_msg, wf_id_dd, handles.wf_dd, wf_json],
    )

    demo.load(load_talent, inputs=[talent_id_dd], outputs=[
        talent_name, talent_personality, talent_tags, talent_prompt, talent_msg,
    ])
    demo.load(load_org, inputs=[org_id_dd], outputs=[
        org_name, org_mission, org_culture, org_talent_ids,
        org_bindings_json, org_directives_json, org_default_wf, org_mapping_json, org_msg,
    ])
    demo.load(load_workflow, inputs=[wf_id_dd], outputs=[wf_json, wf_msg])
