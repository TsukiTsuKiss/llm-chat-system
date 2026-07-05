from __future__ import annotations

import os
from typing import Iterable

SUPPORTED_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".cs", ".php",
    ".rb", ".swift", ".kt", ".scala", ".sql", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".xml", ".html", ".css", ".sh",
    ".bat", ".ps1", ".env", ".log",
}

MAX_UPLOAD_FILES = 5
MAX_FILE_SIZE_BYTES = 256 * 1024
MAX_TOTAL_CHARS = 80000


def to_bool(value) -> bool | None:
    """設定値を bool に変換する。変換不能なら None。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("1", "true", "on", "yes", "y"):
            return True
        if v in ("0", "false", "off", "no", "n"):
            return False
    return None


def stream_default_from_config(config: dict | None, default_value: bool = True) -> bool:
    """config から stream の初期値を解決する（web.stream > ui.stream > stream）。"""
    if not isinstance(config, dict):
        return default_value

    web_cfg = config.get("web")
    if isinstance(web_cfg, dict):
        b = to_bool(web_cfg.get("stream"))
        if b is not None:
            return b

    ui_cfg = config.get("ui")
    if isinstance(ui_cfg, dict):
        b = to_bool(ui_cfg.get("stream"))
        if b is not None:
            return b

    b = to_bool(config.get("stream"))
    return b if b is not None else default_value


def temperature_default_from_config(config: dict | None, default_value: float = 0.7) -> float:
    """config から temperature の初期値を解決する（web.temperature > ui.temperature > temperature）。"""
    if not isinstance(config, dict):
        return default_value

    def _to_temperature(value) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            t = float(value)
        except (TypeError, ValueError):
            return None
        if t < 0.0:
            return 0.0
        if t > 2.0:
            return 2.0
        return t

    web_cfg = config.get("web")
    if isinstance(web_cfg, dict):
        t = _to_temperature(web_cfg.get("temperature"))
        if t is not None:
            return t

    ui_cfg = config.get("ui")
    if isinstance(ui_cfg, dict):
        t = _to_temperature(ui_cfg.get("temperature"))
        if t is not None:
            return t

    t = _to_temperature(config.get("temperature"))
    return t if t is not None else default_value


def normalize_uploaded_files(uploaded_files) -> list[str]:
    if not uploaded_files:
        return []
    if isinstance(uploaded_files, str):
        return [uploaded_files]
    if isinstance(uploaded_files, Iterable):
        return [p for p in uploaded_files if isinstance(p, str)]
    return []


def build_uploaded_context(
    uploaded_files,
    *,
    supported_extensions: set[str] | None = None,
    max_upload_files: int = MAX_UPLOAD_FILES,
    max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> tuple[str, str, list[str]]:
    """アップロードファイルから会話注入用のテキストを生成する。

    Returns: (context, notes, used_file_names)
    """
    extensions = supported_extensions or SUPPORTED_TEXT_EXTENSIONS
    paths = normalize_uploaded_files(uploaded_files)
    if not paths:
        return "", "", []

    notes: list[str] = []
    used_blocks: list[str] = []
    used_names: list[str] = []
    total_chars = 0

    for idx, path in enumerate(paths[:max_upload_files], start=1):
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        if ext and ext not in extensions:
            notes.append(f"- {name}: 未対応拡張子のためスキップ")
            continue

        try:
            size = os.path.getsize(path)
            if size > max_file_size_bytes:
                notes.append(f"- {name}: サイズ超過のためスキップ ({size} bytes)")
                continue

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            notes.append(f"- {name}: 読み込み失敗 ({e})")
            continue

        remain = max_total_chars - total_chars
        if remain <= 0:
            notes.append("- 文字数上限に到達したため以降は省略")
            break

        truncated = False
        if len(content) > remain:
            content = content[:remain]
            truncated = True

        total_chars += len(content)
        if truncated:
            notes.append(f"- {name}: 末尾を切り詰めて取り込み")

        used_names.append(name)
        used_blocks.append(
            f"### File {idx}: {name}\n"
            f"```text\n{content}\n```"
        )

    if not used_blocks:
        info = "\n".join(notes) if notes else ""
        return "", info, []

    context = (
        "\n\n[Uploaded Files Context]\n"
        "以下はユーザーがアップロードしたファイル内容です。"
        "必要に応じて参照し、質問に関連する範囲を優先して回答してください。\n\n"
        + "\n\n".join(used_blocks)
    )
    info = "\n".join(notes)
    return context, info, used_names
