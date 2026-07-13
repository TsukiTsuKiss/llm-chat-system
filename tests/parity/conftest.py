"""Shared fixtures for parity tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def studio_root(tmp_path: Path) -> Path:
    """Minimal project tree with solo org + mock mapping."""
    for name in ("schemas", "talents", "organizations/solo", "studio"):
        src = REPO_ROOT / name
        dest = tmp_path / name
        if src.is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, dirs_exist_ok=True)

    shutil.copy2(REPO_ROOT / "ai_assistants_config.json", tmp_path / "ai_assistants_config.json")
    if (REPO_ROOT / "model_costs.csv").exists():
        shutil.copy2(REPO_ROOT / "model_costs.csv", tmp_path / "model_costs.csv")

    mapping = {"solo_bot": {"assistant": "mock"}}
    (tmp_path / "organizations" / "solo" / "model_mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return tmp_path
