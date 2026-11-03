"""sandbox への保存（見出し形式のファイル名・拡張子対応・動作確認ステップの除外）。"""

from __future__ import annotations

import json
from pathlib import Path

from studio.artifacts import extract_artifacts_from_log, save_sandbox_from_session
from studio.logging import StepMetrics

WEB_APP_TEXT = (
    "## index.html\n\n```html\n<!DOCTYPE html>\n<html></html>\n```\n\n"
    "## styles.css\n\n```css\nbody { margin: 0; }\n```\n\n"
    "## script.js\n\n```javascript\nconsole.log('hi');\n```\n\n"
    "## package.json\n\n```json\n{ \"name\": \"app\" }\n```\n\n"
    "## 実行手順\n\n```bash\nnpm start\n```\n"
)


def _step(talent_id: str, action: str, text: str) -> dict:
    return StepMetrics(
        talent_id=talent_id,
        assistant="mock",
        model=None,
        action=action,
        text=text,
        stream=False,
        elapsed=0.0,
        tokens_in=0,
        tokens_out=0,
        tokens_source="none",
        cost=0.0,
    ).to_log_record()


def _write_log(root: Path, session_id: str, records: list[dict]) -> Path:
    log_dir = root / "sessions"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{session_id}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    return path


def test_heading_filenames_and_web_extensions_are_extracted(tmp_path: Path) -> None:
    log = _write_log(tmp_path, "web", [_step("zen_tou", "MVP設計と核心機能の実装", WEB_APP_TEXT)])
    files = extract_artifacts_from_log(log)
    assert {"index.html", "styles.css", "script.js", "package.json"} <= set(files)
    assert files["package.json"] == '{ "name": "app" }'


def test_unnamed_html_css_json_blocks_keep_their_extension(tmp_path: Path) -> None:
    text = "```html\n<p>x</p>\n```\n\n```css\np { color: red; }\n```\n\n```json\n{\"a\": 1}\n```"
    log = _write_log(tmp_path, "unnamed", [_step("zen_tou", "build", text)])
    exts = {Path(name).suffix for name in extract_artifacts_from_log(log)}
    assert exts == {".html", ".css", ".json"}


def test_verification_step_code_is_not_extracted(tmp_path: Path) -> None:
    records = [
        _step("zen_tou", "MVP設計と核心機能の実装", "## script.js\n\n```javascript\nconst a = 1;\n```"),
        _step("kensa_tashika", "動作確認と改善提案", "```javascript\nconst fix = 2;\n```"),
    ]
    log = _write_log(tmp_path, "verify", records)
    assert list(extract_artifacts_from_log(log)) == ["script.js"]


def test_save_sandbox_from_session_writes_only_sandbox(tmp_path: Path) -> None:
    _write_log(tmp_path, "save", [_step("zen_tou", "build", WEB_APP_TEXT)])
    result = save_sandbox_from_session(tmp_path, "save")
    assert result.ok
    session_dir = tmp_path / "sandbox" / "session_save"
    assert result.session_dir == session_dir
    assert {"index.html", "styles.css", "script.js", "package.json"} <= set(result.files)
    assert (session_dir / "index.html").is_file()
    assert not (tmp_path / "index.html").exists()


def test_save_sandbox_from_session_reports_missing_and_empty(tmp_path: Path) -> None:
    assert not save_sandbox_from_session(tmp_path, "nope").ok
    _write_log(tmp_path, "empty", [_step("zen_tou", "build", "コードなし")])
    assert not save_sandbox_from_session(tmp_path, "empty").ok
