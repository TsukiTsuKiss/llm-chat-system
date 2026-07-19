"""Phase 5h studio_dev meta-sample parity tests (design.md §10.4)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from studio.loader import load_session_context
from studio.schema_validate import validate_schema_document
from studio.validation import ValidationReport

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def studio_dev_root(tmp_path: Path) -> Path:
    for name in (
        "schemas",
        "talents",
        "workflows",
        "organizations/studio_dev",
        "studio",
    ):
        src = REPO_ROOT / name
        dest = tmp_path / name
        if src.is_dir():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, dirs_exist_ok=True)

    shutil.copy2(REPO_ROOT / "ai_assistants_config.json", tmp_path / "ai_assistants_config.json")
    shutil.copy2(
        REPO_ROOT / "organizations" / "studio_dev" / "model_mapping.example.json",
        tmp_path / "organizations" / "studio_dev" / "model_mapping.json",
    )
    return tmp_path


def test_studio_dev_org_loads(studio_dev_root: Path) -> None:
    ctx = load_session_context("studio_dev", studio_dev_root, workflow_id="dev")
    assert ctx.org_id == "studio_dev"
    assert set(ctx.talents) >= {"architect", "implementer", "reviewer"}
    assert ctx.model_mapping["implementer"]["assistant"] == "mock"


def test_studio_dev_meeting_bindings(studio_dev_root: Path) -> None:
    ctx = load_session_context("studio_dev", studio_dev_root, workflow_id="meeting")
    assert "architect" in ctx.talents


def test_studio_phase1_scenario_schema() -> None:
    path = REPO_ROOT / "scenarios" / "studio_phase1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    report = ValidationReport()
    validate_schema_document(data, "scenario", path.name, report)
    assert not report.errors
    assert data["organization"] == "studio_dev"
    assert data["workflow"] == "dev"


def test_studio_dev_corpus_files_exist() -> None:
    corpus = REPO_ROOT / "user_context" / "corpus"
    assert (corpus / "design_summary.md").is_file()
    assert (corpus / "parity_checklist.md").is_file()
    assert (REPO_ROOT / "user_context" / "my_context.example.md").is_file()
