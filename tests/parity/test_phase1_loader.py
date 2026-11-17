"""Phase 1 loader validation parity tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio.loader import load_session_context
from studio.validation import StudioValidationError


def test_solo_org_loads_with_mock(studio_root: Path) -> None:
    ctx = load_session_context("solo", studio_root)
    assert ctx.org_id == "solo"
    assert "solo_bot" in ctx.talents
    assert ctx.model_mapping["solo_bot"]["assistant"] == "mock"


def test_missing_talent_reports_e201(studio_root: Path) -> None:
    config_path = studio_root / "organizations" / "solo" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["talent_ids"] = ["missing_bot"]
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(StudioValidationError) as exc:
        load_session_context("solo", studio_root)
    assert any(e.code == "E201" for e in exc.value.errors)


def test_missing_model_mapping_reports_e202(studio_root: Path) -> None:
    (studio_root / "organizations" / "solo" / "model_mapping.json").unlink()
    with pytest.raises(StudioValidationError) as exc:
        load_session_context("solo", studio_root)
    assert any(e.code == "E202" for e in exc.value.errors)


def test_talent_schema_violation_reports_e102(studio_root: Path) -> None:
    bad = studio_root / "talents" / "bad.json"
    bad.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    with pytest.raises(StudioValidationError) as exc:
        load_session_context("solo", studio_root)
    assert any(e.code == "E102" for e in exc.value.errors)


def test_mapping_profile_loads_named_file_and_keeps_default(studio_root: Path) -> None:
    org = studio_root / "organizations" / "solo"
    default_text = (org / "model_mapping.json").read_text(encoding="utf-8")
    mapping = json.loads(default_text)
    mapping["solo_bot"] = {"assistant": "mock", "model": "profile-model"}
    (org / "model_mapping.alt.json").write_text(json.dumps(mapping), encoding="utf-8")

    ctx = load_session_context("solo", studio_root, mapping_profile="alt")
    assert ctx.mapping_profile == "alt"
    assert ctx.model_mapping["solo_bot"]["model"] == "profile-model"
    assert (org / "model_mapping.json").read_text(encoding="utf-8") == default_text
    assert load_session_context("solo", studio_root).mapping_profile is None


def test_missing_mapping_profile_reports_e202_with_available(studio_root: Path) -> None:
    org = studio_root / "organizations" / "solo"
    (org / "model_mapping.alt.json").write_text((org / "model_mapping.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(StudioValidationError) as exc:
        load_session_context("solo", studio_root, mapping_profile="nope")
    errors = [e for e in exc.value.errors if e.code == "E202"]
    assert errors and "alt" in errors[0].hint


def test_mapping_profile_rejects_path_traversal(studio_root: Path) -> None:
    with pytest.raises(StudioValidationError) as exc:
        load_session_context("solo", studio_root, mapping_profile="../x")
    assert any(e.code == "E202" for e in exc.value.errors)
