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
