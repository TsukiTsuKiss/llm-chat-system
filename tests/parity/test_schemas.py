"""Schema file sanity checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = REPO_ROOT / "schemas"


@pytest.mark.parametrize(
    "schema_file",
    sorted(SCHEMAS.glob("*.schema.json")),
)
def test_schema_is_valid_draft202012(schema_file: Path) -> None:
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_repo_sample_talent_validates() -> None:
    schema = json.loads((SCHEMAS / "talent.schema.json").read_text(encoding="utf-8"))
    data = json.loads((REPO_ROOT / "talents" / "solo_bot.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)


def test_repo_sample_org_validates() -> None:
    schema = json.loads((SCHEMAS / "organization.schema.json").read_text(encoding="utf-8"))
    data = json.loads((REPO_ROOT / "organizations" / "solo" / "config.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)
