"""組織・人材・ワークフローの参照整合性（リポジトリ同梱のファイルだけを見る）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
ORG_CONFIGS = sorted((REPO_ROOT / "organizations").glob("*/config.json"))
TALENT_FILES = sorted((REPO_ROOT / "talents").glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _org_id(path: Path) -> str:
    return path.parent.name


@pytest.mark.parametrize("path", TALENT_FILES, ids=lambda p: p.stem)
def test_talent_validates(path: Path) -> None:
    schema = _load(REPO_ROOT / "schemas" / "talent.schema.json")
    Draft202012Validator(schema).validate(_load(path))


@pytest.mark.parametrize("path", ORG_CONFIGS, ids=_org_id)
def test_org_validates(path: Path) -> None:
    schema = _load(REPO_ROOT / "schemas" / "organization.schema.json")
    Draft202012Validator(schema).validate(_load(path))


@pytest.mark.parametrize("path", ORG_CONFIGS, ids=_org_id)
def test_org_references_resolve(path: Path) -> None:
    config = _load(path)
    talent_ids = config["talent_ids"]
    missing = [i for i in talent_ids if not (REPO_ROOT / "talents" / f"{i}.json").is_file()]
    assert not missing, f"talents/ にない人材: {missing}"

    for workflow, slots in config.get("workflow_bindings", {}).items():
        assert (REPO_ROOT / "workflows" / f"{workflow}.json").is_file(), f"workflows/ にない: {workflow}"
        for slot, ids in slots.items():
            outside = [i for i in ids if i not in talent_ids]
            assert not outside, f"{workflow}.{slot} が talent_ids にない人材を指す: {outside}"

    default = config.get("default_workflow")
    if default:
        assert (REPO_ROOT / "workflows" / f"{default}.json").is_file(), f"default_workflow が workflows/ にない: {default}"


@pytest.mark.parametrize("path", ORG_CONFIGS, ids=_org_id)
def test_model_mapping_example_covers_members(path: Path) -> None:
    example = path.parent / "model_mapping.example.json"
    if not example.is_file():
        pytest.skip("model_mapping.example.json なし")
    assert set(_load(example)) == set(_load(path)["talent_ids"])
