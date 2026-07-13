"""JSON Schema validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from studio.validation import StudioError, ValidationReport

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def schema_path(name: str) -> Path:
    return SCHEMA_DIR / f"{name}.schema.json"


def load_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMA_CACHE:
        path = schema_path(name)
        with path.open(encoding="utf-8") as f:
            _SCHEMA_CACHE[name] = json.load(f)
    return _SCHEMA_CACHE[name]


def validate_schema_document(
    data: Any,
    schema_name: str,
    target: str,
    report: ValidationReport | None = None,
) -> ValidationReport:
    result = report or ValidationReport()
    try:
        schema = load_schema(schema_name)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        result.add(
            StudioError(
                code="E102",
                target=f"schemas/{schema_name}.schema.json",
                message=f"スキーマの読み込みに失敗しました: {exc}",
            )
        )
        return result

    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path_parts = [str(p) for p in error.absolute_path]
        field = ".".join(path_parts) if path_parts else "(root)"
        result.add(
            StudioError(
                code="E102",
                target=target,
                message=f"'{field}' {error.message}",
            )
        )
    return result


def load_json_file(path: Path, report: ValidationReport) -> Any | None:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        report.add(
            StudioError(
                code="E101",
                target=str(path).replace("\\", "/"),
                message=f"{exc.lineno}行目で JSON パースに失敗しました",
            )
        )
        return None
