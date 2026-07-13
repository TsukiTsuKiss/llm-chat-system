"""Persist talents / organizations / workflows with validation (design.md §8.4, §5.2)."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from studio.loader import (
    RESERVED_ASSISTANTS,
    load_ai_assistants,
    load_organization_config,
    scan_talents,
    validate_model_mapping,
    validate_role_directives,
    validate_talent_refs,
    validate_workflow_binding_talent_refs,
)
from studio.schema_validate import validate_schema_document
from studio.validation import StudioError, ValidationReport
from studio.workflow_validate import validate_workflow_structure

ConfigKind = Literal["talent", "organization", "model_mapping", "workflow"]

WORKFLOW_TEMPLATE: dict[str, Any] = {
    "name": "新規ワークフロー",
    "description": "",
    "slots": {
        "participant": {
            "description": "参加者",
            "count": "1+",
        }
    },
    "phases": [
        {
            "type": "serial",
            "steps": [
                {
                    "slot": "participant",
                    "action": "議題について意見を述べる",
                }
            ],
        }
    ],
}

TALENT_TEMPLATE: dict[str, Any] = {
    "name": "新規人材",
    "personality": "",
    "system_prompt": "あなたは新規人材です。",
    "tags": [],
}


@dataclass
class SaveResult:
    ok: bool
    message: str
    path: Path | None = None


def _path_for(
    kind: ConfigKind,
    item_id: str,
    root: Path,
    *,
    org_id: str | None = None,
) -> Path:
    if kind == "talent":
        return root / "talents" / f"{item_id}.json"
    if kind == "workflow":
        return root / "workflows" / f"{item_id}.json"
    if kind == "organization":
        return root / "organizations" / item_id / "config.json"
    if kind == "model_mapping":
        if not org_id:
            raise ValueError("org_id is required for model_mapping")
        return root / "organizations" / org_id / "model_mapping.json"
    raise ValueError(f"unknown kind: {kind}")


def list_configs(kind: ConfigKind, root: Path) -> list[str]:
    root = Path(root)
    if kind == "talent":
        talents_dir = root / "talents"
        if not talents_dir.is_dir():
            return []
        return sorted(path.stem for path in talents_dir.glob("*.json"))
    if kind == "workflow":
        wf_dir = root / "workflows"
        if not wf_dir.is_dir():
            return []
        return sorted(path.stem for path in wf_dir.glob("*.json"))
    if kind == "organization":
        org_dir = root / "organizations"
        if not org_dir.is_dir():
            return []
        return sorted(
            name.name
            for name in org_dir.iterdir()
            if name.is_dir() and (name / "config.json").is_file()
        )
    raise ValueError(f"list_configs does not support kind={kind}")


def load_config(
    kind: ConfigKind,
    item_id: str,
    root: Path,
    *,
    org_id: str | None = None,
) -> dict[str, Any]:
    path = _path_for(kind, item_id, root, org_id=org_id)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def list_assistant_names(root: Path) -> list[str]:
    report = ValidationReport()
    assistants = load_ai_assistants(root, report)
    names = sorted(assistants.keys())
    for reserved in sorted(RESERVED_ASSISTANTS):
        if reserved not in names:
            names.append(reserved)
    return names


def talent_referenced_by_orgs(talent_id: str, root: Path) -> list[str]:
    refs: list[str] = []
    for org_id in list_configs("organization", root):
        org = load_config("organization", org_id, root)
        if talent_id in (org.get("talent_ids") or []):
            refs.append(org_id)
    return refs


def validate_config(
    kind: ConfigKind,
    item_id: str,
    data: dict[str, Any],
    root: Path,
    *,
    org_id: str | None = None,
) -> ValidationReport:
    root = Path(root)
    report = ValidationReport()

    if kind == "talent":
        validate_schema_document(data, "talent", f"talents/{item_id}.json", report)
        return report

    if kind == "workflow":
        validate_schema_document(data, "workflow", f"workflows/{item_id}.json", report)
        if report.ok:
            validate_workflow_structure(item_id, data, report)
        return report

    if kind == "organization":
        validate_schema_document(data, "organization", f"organizations/{item_id}/config.json", report)
        talents = scan_talents(root, report)
        if report.ok:
            validate_talent_refs(item_id, data, talents, report)
            validate_role_directives(item_id, data, report)
            validate_workflow_binding_talent_refs(item_id, data, report)
            default_wf = data.get("default_workflow")
            if default_wf and default_wf not in list_configs("workflow", root):
                report.add(
                    StudioError(
                        code="E207",
                        target=f"organizations/{item_id}/config.json",
                        message=f"default_workflow '{default_wf}' が workflows/ にありません",
                    )
                )
        return report

    if kind == "model_mapping":
        if not org_id:
            report.add(
                StudioError(
                    code="E202",
                    target="model_mapping",
                    message="org_id が未指定です",
                )
            )
            return report
        validate_schema_document(
            data,
            "model_mapping",
            f"organizations/{org_id}/model_mapping.json",
            report,
        )
        org = load_config("organization", org_id, root)
        if not org:
            report.add(
                StudioError(
                    code="E201",
                    target=f"organizations/{org_id}",
                    message="組織 config.json がありません",
                )
            )
            return report
        assistants = load_ai_assistants(root, report)
        if report.ok:
            validate_model_mapping(org_id, org, data, assistants, report)
        return report

    report.add(
        StudioError(code="E102", target=str(kind), message=f"未対応の kind: {kind}")
    )
    return report


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_config(
    kind: ConfigKind,
    item_id: str,
    data: dict[str, Any],
    root: Path,
    *,
    org_id: str | None = None,
) -> SaveResult:
    item_id = (item_id or "").strip()
    if not item_id:
        return SaveResult(False, "ID を入力してください")

    root = Path(root)
    report = validate_config(kind, item_id, data, root, org_id=org_id)
    if not report.ok:
        return SaveResult(False, "\n".join(err.format() for err in report.errors))

    path = _path_for(kind, item_id, root, org_id=org_id)
    _write_json(path, data)
    rel = path.relative_to(root)
    return SaveResult(True, f"✅ 保存しました: {rel}", path)


def delete_config(kind: ConfigKind, item_id: str, root: Path) -> SaveResult:
    item_id = (item_id or "").strip()
    if not item_id:
        return SaveResult(False, "ID を選択してください")

    root = Path(root)

    if kind == "talent":
        refs = talent_referenced_by_orgs(item_id, root)
        if refs:
            return SaveResult(
                False,
                f"❌ 削除できません: {item_id} は組織 {', '.join(refs)} で使用中です",
            )
        path = _path_for("talent", item_id, root)
        if not path.exists():
            return SaveResult(False, f"❌ 見つかりません: {path.relative_to(root)}")
        path.unlink()
        return SaveResult(True, f"✅ 削除しました: {path.relative_to(root)}")

    if kind == "workflow":
        path = _path_for("workflow", item_id, root)
        if not path.exists():
            return SaveResult(False, f"❌ 見つかりません: {path.relative_to(root)}")
        path.unlink()
        return SaveResult(True, f"✅ 削除しました: {path.relative_to(root)}")

    if kind == "organization":
        org_dir = root / "organizations" / item_id
        if not org_dir.is_dir():
            return SaveResult(False, f"❌ 見つかりません: organizations/{item_id}")
        shutil.rmtree(org_dir)
        return SaveResult(True, f"✅ 削除しました: organizations/{item_id}")

    return SaveResult(False, f"❌ delete は kind={kind} 非対応")


def create_talent(item_id: str, root: Path) -> SaveResult:
    item_id = (item_id or "").strip()
    if not item_id:
        return SaveResult(False, "人材 ID を入力してください")
    path = _path_for("talent", item_id, root)
    if path.exists():
        return SaveResult(False, f"❌ 既に存在します: talents/{item_id}.json")
    return save_config("talent", item_id, dict(TALENT_TEMPLATE), root)


def create_workflow(item_id: str, root: Path) -> SaveResult:
    item_id = (item_id or "").strip()
    if not item_id:
        return SaveResult(False, "ワークフロー ID を入力してください")
    path = _path_for("workflow", item_id, root)
    if path.exists():
        return SaveResult(False, f"❌ 既に存在します: workflows/{item_id}.json")
    data = dict(WORKFLOW_TEMPLATE)
    data["name"] = item_id
    return save_config("workflow", item_id, data, root)


def create_organization(
    org_id: str,
    root: Path,
    *,
    initial_talent_id: str,
    name: str = "",
) -> SaveResult:
    org_id = (org_id or "").strip()
    initial_talent_id = (initial_talent_id or "").strip()
    if not org_id:
        return SaveResult(False, "組織 ID を入力してください")
    if not initial_talent_id:
        return SaveResult(False, "初期人材を1つ指定してください")

    root = Path(root)
    org_dir = root / "organizations" / org_id
    if org_dir.exists():
        return SaveResult(False, f"❌ 既に存在します: organizations/{org_id}")

    if initial_talent_id not in list_configs("talent", root):
        return SaveResult(False, f"❌ 人材 '{initial_talent_id}' が talents/ にありません")

    config = {
        "name": name or org_id,
        "talent_ids": [initial_talent_id],
    }
    result = save_config("organization", org_id, config, root)
    if not result.ok:
        return result

    example = root / "organizations" / "solo" / "model_mapping.example.json"
    if not example.exists():
        for candidate in org_dir.parent.glob("*/model_mapping.example.json"):
            example = candidate
            break
    mapping_path = org_dir / "model_mapping.json"
    if example.exists():
        shutil.copy2(example, mapping_path)
        mapping = load_config("model_mapping", "", root, org_id=org_id)
        if initial_talent_id not in mapping:
            mapping[initial_talent_id] = {"assistant": "mock"}
        save_config("model_mapping", "", mapping, root, org_id=org_id)
    else:
        save_config(
            "model_mapping",
            "",
            {initial_talent_id: {"assistant": "mock"}},
            root,
            org_id=org_id,
        )

    return SaveResult(True, f"✅ 組織を作成しました: organizations/{org_id}", org_dir)


def mapping_to_json_text(mapping: dict[str, Any]) -> str:
    return json.dumps(mapping, ensure_ascii=False, indent=2)


def parse_mapping_json(text: str) -> tuple[dict[str, Any] | None, str]:
    try:
        data = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        return None, f"JSON 構文エラー: {exc}"
    if not isinstance(data, dict):
        return None, "model_mapping は JSON オブジェクトである必要があります"
    return data, ""
