"""Gradio settings tab (design.md §8.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gradio as gr

from studio.assistant_availability import (
    assistant_dropdown_choices,
    is_assistant_available,
    load_assistants_catalog,
    model_dropdown_choices,
    unavailable_reason,
)
from studio.config_store import (
    create_organization,
    create_talent,
    create_workflow,
    delete_config,
    list_configs,
    load_config,
    save_config,
)
from studio.mapping_form import (
    build_mapping_payload,
    merge_mapping_for_talents,
    normalize_mapping_entry,
    ordered_talent_ids,
    patch_mapping_entry,
)
from studio.web_ui import load_org_panel, workflow_dropdown_for_org

# 削除・新規作成: 入力欄の横に小さく配置（ラベルと高さを揃えない）
_ACTION_BTN = dict(variant="primary", size="sm", elem_classes=["studio-action-btn"], scale=0, min_width=80)
_SAVE_BTN = dict(variant="primary", elem_classes=["studio-save-btn"])
_ID_ROW = dict(elem_classes=["studio-id-row"])


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


def _chat_workflow_update(root: Path, org_id: str, current_wf: str = ""):
    choices, value = workflow_dropdown_for_org(root, org_id or "", current_wf)
    return gr.update(choices=choices, value=value)


def build_settings_tab(root: Path, handles: SettingsHandles, demo: gr.Blocks) -> None:
    talent_ids = list_configs("talent", root)
    org_ids = list_configs("organization", root)
    wf_ids = list_configs("workflow", root)
    assistants_catalog = load_assistants_catalog(root)

    with gr.Tab("⚙️ 設定編集"):
        with gr.Column(elem_classes=["studio-settings-panel"]):
            gr.Markdown("人材・組織・ワークフローを編集します。保存前にバリデーションを実行します（§8.4）。")

            with gr.Tabs():
                # --- Talent ---
                with gr.Tab("👤 人材"):
                    with gr.Row():
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                talent_id_dd = gr.Dropdown(
                                    label="人材 ID",
                                    choices=talent_ids,
                                    value=talent_ids[0] if talent_ids else None,
                                    allow_custom_value=True,
                                    scale=4,
                                )
                                talent_delete_btn = gr.Button("削除", **_ACTION_BTN)
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                talent_new_id = gr.Textbox(
                                    label="新規 ID",
                                    placeholder="例: my_bot",
                                    scale=4,
                                )
                                talent_create_btn = gr.Button("新規作成", **_ACTION_BTN)
                    talent_name = gr.Textbox(label="name")
                    talent_personality = gr.Textbox(label="personality", lines=2)
                    talent_tags = gr.Textbox(label="tags（カンマ区切り）")
                    talent_prompt = gr.Textbox(label="system_prompt", lines=10)
                    talent_save_btn = gr.Button("保存", **_SAVE_BTN)
                    talent_msg = gr.Markdown("")

                # --- Organization ---
                with gr.Tab("🏢 組織"):
                    with gr.Row():
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                org_id_dd = gr.Dropdown(
                                    label="組織 ID",
                                    choices=org_ids,
                                    value=org_ids[0] if org_ids else None,
                                    allow_custom_value=True,
                                    scale=4,
                                )
                                org_delete_btn = gr.Button("削除", **_ACTION_BTN)
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                org_new_id = gr.Textbox(label="新規組織 ID", scale=3)
                                org_new_talent = gr.Dropdown(
                                    label="初期人材（必須）",
                                    choices=talent_ids,
                                    value=talent_ids[0] if talent_ids else None,
                                    scale=3,
                                )
                                org_create_btn = gr.Button("新規作成", **_ACTION_BTN)
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
                    org_save_btn = gr.Button("組織 config を保存", **_SAVE_BTN)
                    org_mapping_state = gr.State({})
                    org_talent_ids_order = gr.State([])
                    org_mapping_note = gr.Markdown("")

                    mapping_row_ids: list[str] = list(talent_ids)
                    assistant_choices_init, _ = assistant_dropdown_choices(assistants_catalog)
                    mapping_rows: dict[str, tuple[Any, Any, Any]] = {}

                    gr.Markdown("**model_mapping**（talent_ids チェックボックスと同じ順）")
                    for talent_id in mapping_row_ids:
                        with gr.Group(visible=False) as group:
                            with gr.Row():
                                gr.Textbox(value=talent_id, label="人材 ID", interactive=False, scale=2)
                                asst_dd = gr.Dropdown(
                                    label="assistant",
                                    choices=assistant_choices_init,
                                    interactive=True,
                                    scale=3,
                                )
                                model_dd = gr.Dropdown(
                                    label="model",
                                    choices=[],
                                    allow_custom_value=True,
                                    interactive=True,
                                    scale=3,
                                )
                        mapping_rows[talent_id] = (group, asst_dd, model_dd)

                    org_mapping_save_btn = gr.Button("model_mapping を保存", **_SAVE_BTN)
                    org_msg = gr.Markdown("")

                # --- Workflow ---
                with gr.Tab("🔄 ワークフロー"):
                    with gr.Row():
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                wf_id_dd = gr.Dropdown(
                                    label="ワークフロー ID",
                                    choices=wf_ids,
                                    value=wf_ids[0] if wf_ids else None,
                                    allow_custom_value=True,
                                    scale=4,
                                )
                                wf_delete_btn = gr.Button("削除", **_ACTION_BTN)
                        with gr.Group():
                            with gr.Row(**_ID_ROW):
                                wf_new_id = gr.Textbox(label="新規 ID", scale=4)
                                wf_create_btn = gr.Button("新規作成", **_ACTION_BTN)
                    wf_json = gr.Textbox(label="workflows/<id>.json", lines=24)
                    wf_save_btn = gr.Button("保存", **_SAVE_BTN)
                    wf_msg = gr.Markdown("")

    def _talent_pool_ids() -> list[str]:
        return list_configs("talent", root)

    def _mapping_load_bundle(talent_ids_selected: list[str], mapping: dict):
        pool = _talent_pool_ids()
        order = ordered_talent_ids(talent_ids_selected, None, choice_order=pool)
        state: dict[str, dict[str, str]] = {
            talent_id: normalize_mapping_entry(entry)
            for talent_id, entry in (mapping or {}).items()
        }
        for talent_id in order:
            state.setdefault(talent_id, normalize_mapping_entry(None))
        return state, order

    def _sync_mapping_state(
        selected: list[str],
        mapping_state: dict,
        talent_order: list[str],
    ) -> tuple[dict[str, dict[str, str]], list[str]]:
        order = ordered_talent_ids(selected, talent_order, choice_order=_talent_pool_ids())
        state = dict(mapping_state or {})
        for talent_id in order:
            state.setdefault(talent_id, normalize_mapping_entry(None))
        return state, order

    def _mapping_row_output_list() -> list:
        outputs: list = []
        for talent_id in mapping_row_ids:
            group, asst_dd, model_dd = mapping_rows[talent_id]
            outputs.extend([group, asst_dd, model_dd])
        return outputs

    def _noop_row_updates() -> list:
        return [gr.update()] * (3 * len(mapping_row_ids))

    def _mapping_row_updates(selected: list[str], mapping: dict) -> list:
        assistant_choices, _ = assistant_dropdown_choices(assistants_catalog)
        selected_set = set(selected or [])
        updates: list = []
        for talent_id in mapping_row_ids:
            visible = talent_id in selected_set
            entry = normalize_mapping_entry((mapping or {}).get(talent_id)) if visible else {}
            assistant = entry.get("assistant", "mock")
            models = model_dropdown_choices(assistant, assistants_catalog) if visible else []
            model_value = entry.get("model") or (models[0] if models else None)
            updates.extend([
                gr.update(visible=visible),
                gr.update(
                    value=assistant if visible else None,
                    choices=assistant_choices,
                ),
                gr.update(
                    value=model_value if visible else None,
                    choices=models,
                ),
            ])
        return updates

    def _empty_org_mapping_fields():
        return {}, [], *_mapping_row_updates([], {})

    def _make_assistant_handler(talent_id: str):
        def handler(assistant_name: str, state: dict):
            cfg = assistants_catalog.get(assistant_name, {})
            if not is_assistant_available(assistant_name, cfg):
                prev = normalize_mapping_entry((state or {}).get(talent_id))
                models = model_dropdown_choices(prev["assistant"], assistants_catalog)
                reason = unavailable_reason(assistant_name, cfg)
                return (
                    state or {},
                    gr.update(value=prev["assistant"]),
                    gr.update(choices=models, value=prev.get("model")),
                    f"⚠️ `{assistant_name}` は API キー未設定のため選択できません（{reason}）",
                )
            models = model_dropdown_choices(assistant_name, assistants_catalog)
            model_value = models[0] if models else ""
            new_state = patch_mapping_entry(
                state,
                talent_id,
                assistant=assistant_name,
                model=model_value,
            )
            entry = new_state[talent_id]
            return (
                new_state,
                gr.update(),
                gr.update(choices=models, value=entry.get("model")),
                "",
            )

        return handler

    def _make_model_handler(talent_id: str):
        def handler(model_name: str, state: dict):
            return (
                patch_mapping_entry(state, talent_id, model=model_name or ""),
                "",
            )

        return handler

    for _tid in mapping_row_ids:
        _, asst_dd, model_dd = mapping_rows[_tid]
        asst_dd.change(
            _make_assistant_handler(_tid),
            inputs=[asst_dd, org_mapping_state],
            outputs=[org_mapping_state, asst_dd, model_dd, org_mapping_note],
        )
        model_dd.change(
            _make_model_handler(_tid),
            inputs=[model_dd, org_mapping_state],
            outputs=[org_mapping_state, org_mapping_note],
        )

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
            base = ("", "", "", [], "{}", "{}", "", {}, [], "")
        else:
            data = load_config("organization", org_id, root)
            mapping = load_config("model_mapping", "", root, org_id=org_id)
            talent_ids_selected = data.get("talent_ids") or []
            merged, order = _mapping_load_bundle(talent_ids_selected, mapping)
            extra = {
                "common_directives": data.get("common_directives", []),
                "role_directives": data.get("role_directives", {}),
            }
            base = (
                data.get("name", ""),
                data.get("mission", ""),
                _list_to_lines(data.get("culture")),
                talent_ids_selected,
                json.dumps(data.get("workflow_bindings") or {}, ensure_ascii=False, indent=2),
                json.dumps(extra, ensure_ascii=False, indent=2),
                data.get("default_workflow") or "",
                merged,
                order,
                "",
            )
        return base

    def _build_org_config(
        name: str,
        mission: str,
        culture: str,
        talent_ids_selected: list[str],
        bindings_json: str,
        directives_json: str,
        default_wf: str,
        talent_order: list[str],
    ) -> tuple[dict[str, Any] | None, str]:
        if not talent_ids_selected:
            return None, "talent_ids を1つ以上選択してください"
        config: dict[str, Any] = {
            "talent_ids": ordered_talent_ids(
                talent_ids_selected,
                talent_order,
                choice_order=_talent_pool_ids(),
            ),
        }
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

    def save_org(org_id: str, chat_wf: str, mapping_state: dict, talent_order: list[str], *fields):
        config, err = _build_org_config(*fields, talent_order)
        if config is None:
            return err, gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), *_noop_row_updates()
        result = save_config("organization", org_id, config, root)
        orgs = list_configs("organization", root)
        org_upd = gr.update(
            choices=orgs,
            value=org_id if result.ok and org_id in orgs else (orgs[0] if orgs else None),
        )
        choices, wf_value = workflow_dropdown_for_org(root, org_id, chat_wf)
        wf_upd = gr.update(choices=choices, value=wf_value)
        talents_text = load_org_panel(root, org_id, wf_value)[0] if result.ok else gr.update()
        if result.ok:
            order = list(config["talent_ids"])
            state = _sync_mapping_state(order, mapping_state, order)[0]
            return (
                result.message,
                org_upd,
                wf_upd,
                talents_text,
                state,
                order,
                *_mapping_row_updates(order, state),
            )
        return result.message, org_upd, wf_upd, talents_text, gr.update(), gr.update(), *_noop_row_updates()

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
        inputs=[org_id_dd, handles.wf_dd, org_mapping_state, org_talent_ids_order, *org_fields],
        outputs=[
            org_msg,
            handles.org_dd,
            handles.wf_dd,
            handles.talents_md,
            org_mapping_state,
            org_talent_ids_order,
            *_mapping_row_output_list(),
        ],
    )

    def save_org_mapping(org_id: str, talent_ids_selected: list[str], mapping_state: dict):
        if not org_id:
            return "組織 ID を選択してください", gr.update(), gr.update(), *_noop_row_updates()
        if not talent_ids_selected:
            return "talent_ids を1つ以上選択してください", gr.update(), gr.update(), *_noop_row_updates()
        ordered = ordered_talent_ids(
            talent_ids_selected,
            None,
            choice_order=_talent_pool_ids(),
        )
        payload = build_mapping_payload(ordered, mapping_state)
        result = save_config("model_mapping", "", payload, root, org_id=org_id)
        talents_text = load_org_panel(root, org_id, "")[0] if result.ok else gr.update()
        if result.ok:
            state = dict(mapping_state or {})
            state.update(payload)
            return result.message, talents_text, state, *_mapping_row_updates(talent_ids_selected, state)
        return result.message, talents_text, gr.update(), *_noop_row_updates()

    org_mapping_save_btn.click(
        save_org_mapping,
        inputs=[org_id_dd, org_talent_ids, org_mapping_state],
        outputs=[org_msg, handles.talents_md, org_mapping_state, *_mapping_row_output_list()],
    )

    def on_talent_ids_change(selected: list[str], mapping_state: dict, talent_order: list[str]):
        return _sync_mapping_state(selected, mapping_state, talent_order)

    def refresh_mapping_rows(selected: list[str], mapping_state: dict):
        return _mapping_row_updates(selected, mapping_state)

    org_talent_ids.input(
        on_talent_ids_change,
        inputs=[org_talent_ids, org_mapping_state, org_talent_ids_order],
        outputs=[org_mapping_state, org_talent_ids_order],
    ).then(
        refresh_mapping_rows,
        inputs=[org_talent_ids, org_mapping_state],
        outputs=_mapping_row_output_list(),
    )

    def on_org_create(new_id: str, initial_talent: str, name: str, chat_wf: str):
        result = create_organization(new_id, root, initial_talent_id=initial_talent, name=name)
        orgs = list_configs("organization", root)
        org_dd_upd = gr.update(
            choices=orgs,
            value=new_id if result.ok and new_id in orgs else (orgs[0] if orgs else None),
        )
        chat_org_upd = org_dd_upd
        target_org = new_id if result.ok and new_id in orgs else (orgs[0] if orgs else "")
        wf_upd = _chat_workflow_update(root, target_org, chat_wf)
        if result.ok:
            loaded = load_org(new_id)
            return (
                result.message,
                org_dd_upd,
                chat_org_upd,
                wf_upd,
                *loaded,
                *_mapping_row_updates(loaded[3], loaded[7]),
            )
        return (result.message, org_dd_upd, chat_org_upd, wf_upd, "", "", "", [], "{}", "{}", "", *_empty_org_mapping_fields())

    org_create_btn.click(
        on_org_create,
        inputs=[org_new_id, org_new_talent, org_name, handles.wf_dd],
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
            org_mapping_state,
            org_talent_ids_order,
            *_mapping_row_output_list(),
        ],
    )

    def on_org_delete(org_id: str, chat_wf: str):
        result = delete_config("organization", org_id, root)
        orgs = list_configs("organization", root)
        next_org = orgs[0] if orgs else ""
        org_dd_upd = gr.update(choices=orgs, value=next_org or None)
        chat_org_upd = org_dd_upd
        wf_upd = _chat_workflow_update(root, next_org, chat_wf)
        return (
            result.message,
            org_dd_upd,
            chat_org_upd,
            wf_upd,
            "",
            "",
            "",
            [],
            "{}",
            "{}",
            "",
            *_empty_org_mapping_fields(),
        )

    org_delete_btn.click(
        on_org_delete,
        inputs=[org_id_dd, handles.wf_dd],
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
            org_mapping_state,
            org_talent_ids_order,
            *_mapping_row_output_list(),
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
            org_mapping_state,
            org_talent_ids_order,
            org_msg,
        ],
    ).then(
        refresh_mapping_rows,
        inputs=[org_talent_ids, org_mapping_state],
        outputs=_mapping_row_output_list(),
    )

    def load_workflow(wf_id: str):
        if not wf_id:
            return "", ""
        data = load_config("workflow", wf_id, root)
        return json.dumps(data, ensure_ascii=False, indent=2), ""

    def save_workflow(wf_id: str, text: str, org_id: str, chat_wf: str):
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            return f"JSON 構文エラー: {exc}", gr.update()
        if not isinstance(data, dict):
            return "ワークフローは JSON オブジェクトである必要があります", gr.update()
        result = save_config("workflow", wf_id, data, root)
        wf_upd = _chat_workflow_update(root, org_id, chat_wf)
        return result.message, wf_upd

    wf_id_dd.change(load_workflow, inputs=[wf_id_dd], outputs=[wf_json, wf_msg])
    wf_save_btn.click(
        save_workflow,
        inputs=[wf_id_dd, wf_json, org_id_dd, handles.wf_dd],
        outputs=[wf_msg, handles.wf_dd],
    )

    def on_wf_create(new_id: str, org_id: str, chat_wf: str):
        result = create_workflow(new_id, root)
        ids = list_configs("workflow", root)
        dd_upd = gr.update(choices=ids, value=new_id if result.ok else (ids[0] if ids else None))
        wf_chat_upd = _chat_workflow_update(root, org_id, chat_wf)
        if result.ok:
            return result.message, dd_upd, wf_chat_upd, load_workflow(new_id)[0]
        return result.message, dd_upd, wf_chat_upd, ""

    wf_create_btn.click(
        on_wf_create,
        inputs=[wf_new_id, org_id_dd, handles.wf_dd],
        outputs=[wf_msg, wf_id_dd, handles.wf_dd, wf_json],
    )

    def on_wf_delete(wf_id: str, org_id: str, chat_wf: str):
        result = delete_config("workflow", wf_id, root)
        ids = list_configs("workflow", root)
        dd_upd = gr.update(choices=ids, value=ids[0] if ids else None)
        wf_chat_upd = _chat_workflow_update(root, org_id, chat_wf)
        return result.message, dd_upd, wf_chat_upd, ""

    wf_delete_btn.click(
        on_wf_delete,
        inputs=[wf_id_dd, org_id_dd, handles.wf_dd],
        outputs=[wf_msg, wf_id_dd, handles.wf_dd, wf_json],
    )

    demo.load(load_talent, inputs=[talent_id_dd], outputs=[
        talent_name, talent_personality, talent_tags, talent_prompt, talent_msg,
    ])
    demo.load(load_org, inputs=[org_id_dd], outputs=[
        org_name, org_mission, org_culture, org_talent_ids,
        org_bindings_json, org_directives_json, org_default_wf,
        org_mapping_state, org_talent_ids_order, org_msg,
    ]).then(
        refresh_mapping_rows,
        inputs=[org_talent_ids, org_mapping_state],
        outputs=_mapping_row_output_list(),
    )
    demo.load(load_workflow, inputs=[wf_id_dd], outputs=[wf_json, wf_msg])
