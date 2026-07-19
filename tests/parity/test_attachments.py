"""Attachment file reading parity tests."""

from __future__ import annotations

from pathlib import Path

from studio.loader import read_attachment_files


def test_read_attachment_directory_expands(studio_root: Path) -> None:
    context, report = read_attachment_files([Path("schemas")], {"max_files": 5})
    assert not report.errors
    assert "schemas/talent.schema.json" in context
    assert "schemas/workflow.schema.json" in context


def test_read_attachment_single_file(studio_root: Path) -> None:
    path = Path("schemas/talent.schema.json")
    context, report = read_attachment_files([path], {"max_files": 5})
    assert not report.errors
    assert "Talent" in context
