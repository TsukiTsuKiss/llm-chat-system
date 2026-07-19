"""Web UI helpers for user_context RAG (design.md Appendix D.10)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio.user_context_rag import (
    RagChunk,
    chunks_path,
    corpus_dir,
    global_rag_enabled,
    reindex_corpus,
    resolve_rag_context,
)

CORPUS_PREVIEW_MAX_CHARS = 8000
CHUNK_PREVIEW_MAX_CHARS = 600
CORPUS_PREVIEW_PLACEHOLDER = "_ファイルを選ぶとプレビューが表示されます_"

RAG_DISABLED_HINT = (
    "_`studio_config.json` の `user_context.rag.enabled` を `true` にしてください。"
    " 保存後は **設定を再読込** を押すかページを更新してください。_"
)


@dataclass(frozen=True)
class RagUiState:
    studio_config: dict[str, Any]
    available: bool
    panel_md: str
    default_rag: bool
    corpus_files: list[str]
    corpus_file: str | None
    corpus_preview: str
    status_hint: str


def load_studio_config_for_ui(root: Path) -> dict[str, Any]:
    from studio.loader import load_studio_config
    from studio.validation import StudioValidationError

    try:
        return load_studio_config(root)
    except StudioValidationError:
        return {}


def build_rag_ui_state(root: Path, *, load_corpus_preview: bool = False) -> RagUiState:
    from web_input_utils import user_context_rag_default_from_config

    config = load_studio_config_for_ui(root)
    available = rag_available_in_config(config)
    files = list_corpus_files(root, config)
    first = files[0] if files else None
    panel = corpus_panel_markdown(root, config) if available else RAG_DISABLED_HINT
    default_rag = user_context_rag_default_from_config(config) if available else False
    if load_corpus_preview and first:
        preview = read_corpus_file(root, config, first)
    else:
        preview = CORPUS_PREVIEW_PLACEHOLDER if files else ""
    hint = "" if available else RAG_DISABLED_HINT
    return RagUiState(
        studio_config=config,
        available=available,
        panel_md=panel,
        default_rag=default_rag,
        corpus_files=files,
        corpus_file=first,
        corpus_preview=preview,
        status_hint=hint,
    )


def rag_available_in_config(studio_config: dict[str, Any]) -> bool:
    return global_rag_enabled(studio_config)


def rag_default_from_config(studio_config: dict[str, Any], *, default_value: bool = True) -> bool:
    if not rag_available_in_config(studio_config):
        return False
    return default_value


def list_corpus_files(root: Path, studio_config: dict[str, Any]) -> list[str]:
    corpus = corpus_dir(root, studio_config)
    if not corpus.is_dir():
        return []
    return sorted(path.name for path in corpus.glob("*.md"))


def read_corpus_file(
    root: Path,
    studio_config: dict[str, Any],
    filename: str | None,
    *,
    max_chars: int = CORPUS_PREVIEW_MAX_CHARS,
) -> str:
    if not filename:
        return ""
    corpus = corpus_dir(root, studio_config)
    path = (corpus / filename).resolve()
    if not path.is_file() or path.parent != corpus.resolve():
        return "_ファイルが見つかりません_"
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n…（プレビューは先頭のみ）"


def index_status_text(root: Path, studio_config: dict[str, Any]) -> str:
    path = chunks_path(root, studio_config)
    if not path.is_file():
        return "index: 未構築（「index 再構築」を実行してください）"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "index: 読み込みエラー"
    chunk_count = len(data.get("chunks") or [])
    built_at = str(data.get("built_at") or "不明")
    return f"index: {chunk_count} chunks（built: {built_at}）"


def format_chunks_markdown(
    chunks: tuple[RagChunk, ...] | list[RagChunk],
    *,
    title: str = "RAG ヒット",
    empty_message: str = "_ヒットなし_",
) -> str:
    if not chunks:
        return empty_message
    lines = [f"**{title}** ({len(chunks)} 件)"]
    for chunk in chunks:
        preview = chunk.text
        if len(preview) > CHUNK_PREVIEW_MAX_CHARS:
            preview = preview[:CHUNK_PREVIEW_MAX_CHARS].rstrip() + "\n\n…"
        lines.append(f"\n---\n**{chunk.source}** (score: {chunk.score:.2f})\n\n{preview}")
    return "\n".join(lines)


def search_preview_markdown(
    root: Path,
    studio_config: dict[str, Any],
    query: str,
    *,
    user_context: bool = True,
    user_context_rag: bool = True,
) -> str:
    query = (query or "").strip()
    if not query:
        return "_検索クエリを入力してください_"
    resolution = resolve_rag_context(
        root,
        studio_config,
        query,
        no_user_context=not user_context,
        no_user_context_rag=not user_context_rag,
    )
    if not resolution.enabled:
        return "_RAG は無効です（設定またはトグルを確認）_"
    return format_chunks_markdown(resolution.chunks, title="検索プレビュー")


def last_injection_markdown(chunks: tuple[RagChunk, ...] | list[RagChunk]) -> str:
    return format_chunks_markdown(
        chunks,
        title="直近の注入 chunk",
        empty_message="_（RAG ヒットなし、または RAG 無効）_",
    )


def run_reindex(root: Path, studio_config: dict[str, Any] | None = None) -> str:
    config = studio_config if studio_config is not None else load_studio_config_for_ui(root)
    if not rag_available_in_config(config):
        return f"**エラー** — RAG が無効です。{RAG_DISABLED_HINT}"
    result = reindex_corpus(root, config)
    status = index_status_text(root, studio_config)
    if result.ok:
        return f"{result.message}\n\n{status}"
    return f"**エラー** — {result.message}"


def corpus_panel_markdown(root: Path, studio_config: dict[str, Any]) -> str:
    files = list_corpus_files(root, studio_config)
    corpus = corpus_dir(root, studio_config)
    lines = [
        f"**corpus** — `{corpus}`",
        index_status_text(root, studio_config),
    ]
    if files:
        lines.append("\n**ファイル:** " + ", ".join(f"`{name}`" for name in files))
    else:
        lines.append("\n_corpus に .md ファイルがありません_")
    return "\n".join(lines)
