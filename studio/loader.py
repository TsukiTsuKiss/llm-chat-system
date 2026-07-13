"""Definition loading and cross-reference validation (design.md 5.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from studio.bindings import validate_workflow_binding_talent_refs, validate_workflow_bindings
from studio.schema_validate import load_json_file, validate_schema_document
from studio.validation import StudioError, StudioValidationError, ValidationReport
from studio.workflow_validate import validate_workflow_structure

RESERVED_ASSISTANTS = frozenset({"human", "mock"})
AI_ASSISTANTS_FILE = "ai_assistants_config.json"
STUDIO_CONFIG_FILE = "studio_config.json"
STUDIO_CONFIG_EXAMPLE = "studio_config.example.json"


@dataclass
class SessionContext:
    root: Path
    org_id: str
    org: dict[str, Any]
    talents: dict[str, dict[str, Any]]
    model_mapping: dict[str, dict[str, str]]
    assistants: dict[str, dict[str, Any]]
    studio_config: dict[str, Any]
    workflow_id: str | None = None
    workflow: dict[str, Any] | None = None
    slot_bindings: dict[str, list[str]] | None = None


@dataclass
class StudioPaths:
    root: Path = field(default_factory=lambda: Path("."))

    @property
    def talents_dir(self) -> Path:
        return self.root / "talents"

    @property
    def organizations_dir(self) -> Path:
        return self.root / "organizations"

    @property
    def workflows_dir(self) -> Path:
        return self.root / "workflows"

    @property
    def schemas_dir(self) -> Path:
        return self.root / "schemas"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"


def load_ai_assistants(root: Path, report: ValidationReport) -> dict[str, dict[str, Any]]:
    path = root / AI_ASSISTANTS_FILE
    if not path.exists():
        report.add(
            StudioError(
                code="E401",
                target=AI_ASSISTANTS_FILE,
                message="ファイルが見つかりません",
            )
        )
        return {}
    data = load_json_file(path, report)
    if data is None or not isinstance(data, dict):
        return {}
    return data


def scan_talents(root: Path, report: ValidationReport) -> dict[str, dict[str, Any]]:
    talents: dict[str, dict[str, Any]] = {}
    talents_dir = root / "talents"
    if not talents_dir.is_dir():
        return talents

    for path in sorted(talents_dir.glob("*.json")):
        talent_id = path.stem
        data = load_json_file(path, report)
        if data is None:
            continue
        validate_schema_document(data, "talent", f"talents/{path.name}", report)
        talents[talent_id] = data
    return talents


def load_organization_config(org_id: str, root: Path, report: ValidationReport) -> dict[str, Any] | None:
    path = root / "organizations" / org_id / "config.json"
    if not path.exists():
        report.add(
            StudioError(
                code="E201",
                target=f"organizations/{org_id}",
                message=f"組織 '{org_id}' の config.json がありません",
            )
        )
        return None
    data = load_json_file(path, report)
    if data is None:
        return None
    validate_schema_document(data, "organization", f"organizations/{org_id}/config.json", report)
    return data


def load_model_mapping(org_id: str, root: Path, report: ValidationReport) -> dict[str, dict[str, str]]:
    path = root / "organizations" / org_id / "model_mapping.json"
    example = root / "organizations" / org_id / "model_mapping.example.json"
    if not path.exists():
        report.add(
            StudioError(
                code="E202",
                target=f"organizations/{org_id}/model_mapping.json",
                message="モデル割当ファイルがありません",
                hint=f"{example.name} をコピーして作成してください" if example.exists() else "",
            )
        )
        return {}
    data = load_json_file(path, report)
    if data is None:
        return {}
    validate_schema_document(data, "model_mapping", f"organizations/{org_id}/model_mapping.json", report)
    if isinstance(data, dict):
        return data
    return {}


def load_studio_config(root: Path) -> dict[str, Any]:
    path = root / STUDIO_CONFIG_FILE
    if not path.exists():
        path = root / STUDIO_CONFIG_EXAMPLE
    if not path.exists():
        return {"stream": True, "temperature": 0.7, "max_parallel_calls": 8}
    report = ValidationReport()
    data = load_json_file(path, report)
    if data is None:
        return {"stream": True, "temperature": 0.7, "max_parallel_calls": 8}
    validate_schema_document(data, "studio_config", path.name, report)
    if not report.ok:
        raise StudioValidationError(report.errors)
    return data


def validate_model_mapping(
    org_id: str,
    org: dict[str, Any],
    mapping: dict[str, dict[str, str]],
    assistants: dict[str, dict[str, Any]],
    report: ValidationReport,
) -> None:
    talent_ids = org.get("talent_ids") or []
    for talent_id in talent_ids:
        entry = mapping.get(talent_id)
        if not entry:
            report.add(
                StudioError(
                    code="E202",
                    target=f"organizations/{org_id}",
                    message=f"talent '{talent_id}' のモデル割当がありません",
                    hint="model_mapping.json に追加してください",
                )
            )
            continue

        assistant = entry.get("assistant", "")
        if assistant in RESERVED_ASSISTANTS:
            continue

        if assistant not in assistants:
            report.add(
                StudioError(
                    code="E203",
                    target="model_mapping",
                    message=f"'{assistant}' は {AI_ASSISTANTS_FILE} にありません",
                )
            )
            continue

        if not entry.get("model"):
            report.add(
                StudioError(
                    code="E204",
                    target="model_mapping",
                    message=f"'{talent_id}' の model が未指定です",
                    hint="assistant が human / mock 以外の場合は必須",
                )
            )


def validate_role_directives(org_id: str, org: dict[str, Any], report: ValidationReport) -> None:
    talent_ids = set(org.get("talent_ids") or [])
    for key in (org.get("role_directives") or {}):
        if key not in talent_ids:
            report.add(
                StudioError(
                    code="E206",
                    target=f"organizations/{org_id}",
                    message=f"role_directives の '{key}' が talent_ids に含まれていません",
                )
            )


def validate_talent_refs(org_id: str, org: dict[str, Any], talents: dict[str, Any], report: ValidationReport) -> None:
    for talent_id in org.get("talent_ids") or []:
        if talent_id not in talents:
            report.add(
                StudioError(
                    code="E201",
                    target=f"organizations/{org_id}",
                    message=f"talent '{talent_id}' が talents/ にありません",
                    hint=f"talents/{talent_id}.json を作成するか talent_ids から削除してください",
                )
            )


def load_workflow(workflow_id: str, root: Path, report: ValidationReport) -> dict[str, Any] | None:
    path = root / "workflows" / f"{workflow_id}.json"
    if not path.exists():
        report.add(
            StudioError(
                code="E207",
                target=f"workflows/{workflow_id}.json",
                message=f"ワークフロー '{workflow_id}' が workflows/ にありません",
            )
        )
        return None
    data = load_json_file(path, report)
    if data is None:
        return None
    validate_schema_document(data, "workflow", f"workflows/{workflow_id}.json", report)
    if data is not None:
        validate_workflow_structure(workflow_id, data, report)
    return data


def load_session_context(
    org_id: str,
    root: Path | str = ".",
    *,
    workflow_id: str | None = None,
) -> SessionContext:
    root_path = Path(root)
    report = ValidationReport()

    talents = scan_talents(root_path, report)
    org = load_organization_config(org_id, root_path, report)
    mapping = load_model_mapping(org_id, root_path, report)
    assistants = load_ai_assistants(root_path, report)

    if org:
        validate_talent_refs(org_id, org, talents, report)
        validate_model_mapping(org_id, org, mapping, assistants, report)
        validate_role_directives(org_id, org, report)
        validate_workflow_binding_talent_refs(org_id, org, report)

        workflow = None
        slot_bindings = None
        if workflow_id:
            workflow = load_workflow(workflow_id, root_path, report)
            if workflow:
                slot_bindings = validate_workflow_bindings(
                    org_id, org, workflow_id, workflow, report
                )
    else:
        workflow = None
        slot_bindings = None

    if not report.ok:
        raise StudioValidationError(report.errors)

    studio_config = load_studio_config(root_path)

    return SessionContext(
        root=root_path,
        org_id=org_id,
        org=org or {},
        talents=talents,
        model_mapping=mapping,
        assistants=assistants,
        studio_config=studio_config,
        workflow_id=workflow_id,
        workflow=workflow if workflow_id else None,
        slot_bindings=slot_bindings,
    )


def read_attachment_files(
    paths: list[Path],
    limits: dict[str, int],
) -> tuple[str, ValidationReport]:
    report = ValidationReport()
    max_files = limits.get("max_files", 5)
    max_file_size_kb = limits.get("max_file_size_kb", 256)
    max_total_chars = limits.get("max_total_chars", 80000)

    if len(paths) > max_files:
        report.add(
            StudioError(
                code="E402",
                target="--files",
                message=f"添付ファイル数が上限 ({max_files}) を超えています",
            )
        )
        return "", report

    chunks: list[str] = []
    total_chars = 0
    for path in paths:
        if not path.exists():
            report.add(
                StudioError(
                    code="E101",
                    target=str(path),
                    message="ファイルが見つかりません",
                )
            )
            continue
        size_kb = path.stat().st_size / 1024
        if size_kb > max_file_size_kb:
            report.add(
                StudioError(
                    code="E402",
                    target=str(path),
                    message=f"ファイルサイズが上限 ({max_file_size_kb}KB) を超えています",
                )
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            report.add(
                StudioError(
                    code="E101",
                    target=str(path),
                    message="UTF-8 テキストとして読み込めません",
                )
            )
            continue
        total_chars += len(text)
        if total_chars > max_total_chars:
            report.add(
                StudioError(
                    code="E402",
                    target="--files",
                    message=f"添付文字数合計が上限 ({max_total_chars}) を超えています",
                )
            )
            break
        chunks.append(f"### {path.name}\n{text}")

    return "\n\n".join(chunks), report
