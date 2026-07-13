"""config_store save/load/delete parity tests (design.md §8.4, §9.3)."""

from __future__ import annotations

from pathlib import Path

from studio.config_store import (
    create_talent,
    create_workflow,
    delete_config,
    list_configs,
    load_config,
    save_config,
    talent_referenced_by_orgs,
)
from studio.loader import load_session_context


def test_save_and_load_talent(studio_root: Path) -> None:
    result = save_config(
        "talent",
        "test_bot",
        {
            "name": "Test",
            "system_prompt": "hello",
            "tags": ["a"],
        },
        studio_root,
    )
    assert result.ok
    assert "test_bot" in list_configs("talent", studio_root)
    loaded = load_config("talent", "test_bot", studio_root)
    assert loaded["name"] == "Test"


def test_save_workflow_validates_structure(studio_root: Path) -> None:
    bad = {"name": "x", "slots": {}, "phases": []}
    result = save_config("workflow", "bad_wf", bad, studio_root)
    assert not result.ok


def test_save_workflow_roundtrip(studio_root: Path) -> None:
    assert create_workflow("parity_wf", studio_root).ok
    from studio.loader import load_workflow
    from studio.validation import ValidationReport

    loaded = load_workflow("parity_wf", studio_root, ValidationReport())
    assert loaded is not None
    assert delete_config("workflow", "parity_wf", studio_root).ok


def test_delete_talent_blocked_when_referenced(studio_root: Path) -> None:
    assert talent_referenced_by_orgs("solo_bot", studio_root) == ["solo"]
    result = delete_config("talent", "solo_bot", studio_root)
    assert not result.ok


def test_create_talent_and_delete(studio_root: Path) -> None:
    assert create_talent("temp_bot", studio_root).ok
    assert delete_config("talent", "temp_bot", studio_root).ok
    assert "temp_bot" not in list_configs("talent", studio_root)


def test_create_workflow_json(studio_root: Path) -> None:
    assert create_workflow("temp_wf", studio_root).ok
    data = load_config("workflow", "temp_wf", studio_root)
    assert data.get("slots")
    assert delete_config("workflow", "temp_wf", studio_root).ok


def test_save_organization_updates_session_context(studio_root: Path) -> None:
    org = load_config("organization", "solo", studio_root)
    org["mission"] = "test mission"
    result = save_config("organization", "solo", org, studio_root)
    assert result.ok
    ctx = load_session_context("solo", studio_root)
    assert ctx.org.get("mission") == "test mission"


def test_save_model_mapping_uses_org_id_not_item_id(studio_root: Path) -> None:
    mapping = {"solo_bot": {"assistant": "mock"}}
    result = save_config("model_mapping", "", mapping, studio_root, org_id="solo")
    assert result.ok
    loaded = load_config("model_mapping", "", studio_root, org_id="solo")
    assert loaded["solo_bot"]["assistant"] == "mock"
