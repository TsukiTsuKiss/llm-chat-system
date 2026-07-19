"""User context RAG — corpus index and retrieval (design.md Appendix D.10)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CORPUS_DIR = "user_context/corpus"
DEFAULT_INDEX_DIR = "user_context/index"
CHUNKS_FILE = "chunks.json"
MAX_CHUNK_CHARS = 2000
INDEX_VERSION = 1


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    source: str
    text: str
    score: float


@dataclass(frozen=True)
class ReindexResult:
    ok: bool
    message: str
    chunk_count: int = 0


@dataclass(frozen=True)
class RagResolution:
    enabled: bool
    text: str | None
    chunks: tuple[RagChunk, ...]


def _rag_config(studio_config: dict[str, Any]) -> dict[str, Any]:
    uc = studio_config.get("user_context") or {}
    rag = uc.get("rag") or {}
    return rag if isinstance(rag, dict) else {}


def corpus_dir(root: Path, studio_config: dict[str, Any]) -> Path:
    rag = _rag_config(studio_config)
    rel = str(rag.get("corpus_dir") or DEFAULT_CORPUS_DIR)
    return (root.resolve() / rel).resolve()


def index_dir(root: Path, studio_config: dict[str, Any]) -> Path:
    rag = _rag_config(studio_config)
    rel = str(rag.get("index_dir") or DEFAULT_INDEX_DIR)
    return (root.resolve() / rel).resolve()


def chunks_path(root: Path, studio_config: dict[str, Any]) -> Path:
    return index_dir(root, studio_config) / CHUNKS_FILE


def global_rag_enabled(studio_config: dict[str, Any]) -> bool:
    return bool(_rag_config(studio_config).get("enabled", False))


def session_rag_enabled(
    studio_config: dict[str, Any],
    *,
    no_user_context: bool = False,
    no_user_context_rag: bool = False,
) -> bool:
    if no_user_context or no_user_context_rag:
        return False
    return global_rag_enabled(studio_config)


def rag_top_k(studio_config: dict[str, Any]) -> int:
    raw = _rag_config(studio_config).get("top_k", 5)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 5
    return max(1, value)


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens: set[str] = set(re.findall(r"[\w]+", lowered, flags=re.UNICODE))
    for seq in re.findall(r"[\u3040-\u9fff\u3400-\u4dbf]+", lowered):
        if len(seq) >= 2:
            tokens.add(seq)
        for i in range(len(seq) - 1):
            tokens.add(seq[i : i + 2])
    return tokens


def _score_query(query: str, chunk_text: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    chunk_tokens = _tokenize(chunk_text)
    if not chunk_tokens:
        return 0.0
    overlap = len(query_tokens & chunk_tokens)
    return overlap / len(query_tokens)


def _split_markdown(text: str, source: str) -> list[dict[str, str]]:
    sections = re.split(r"(?m)^(?=## )", text.strip())
    raw_parts: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= MAX_CHUNK_CHARS:
            raw_parts.append(section)
            continue
        paragraphs = re.split(r"\n{2,}", section)
        buffer = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            candidate = f"{buffer}\n\n{para}".strip() if buffer else para
            if len(candidate) <= MAX_CHUNK_CHARS:
                buffer = candidate
            else:
                if buffer:
                    raw_parts.append(buffer)
                buffer = para if len(para) <= MAX_CHUNK_CHARS else para[:MAX_CHUNK_CHARS]
        if buffer:
            raw_parts.append(buffer)

    chunks: list[dict[str, str]] = []
    for idx, part in enumerate(raw_parts):
        chunks.append(
            {
                "chunk_id": f"{source}#{idx}",
                "source": source,
                "text": part,
            }
        )
    return chunks


def reindex_corpus(root: Path, studio_config: dict[str, Any]) -> ReindexResult:
    corpus = corpus_dir(root, studio_config)
    if not corpus.is_dir():
        return ReindexResult(False, f"corpus ディレクトリが見つかりません: {corpus}")

    all_chunks: list[dict[str, str]] = []
    md_files = sorted(corpus.glob("*.md"))
    if not md_files:
        return ReindexResult(False, f"corpus に .md ファイルがありません: {corpus}")

    for path in md_files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        all_chunks.extend(_split_markdown(text, path.name))

    if not all_chunks:
        return ReindexResult(False, "インデックス対象の chunk がありません")

    out_dir = index_dir(root, studio_config)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": INDEX_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "chunks": all_chunks,
    }
    chunks_path(root, studio_config).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ReindexResult(True, f"{len(all_chunks)} chunk を index に保存しました", len(all_chunks))


def _load_index(root: Path, studio_config: dict[str, Any]) -> list[dict[str, str]]:
    path = chunks_path(root, studio_config)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = data.get("chunks") or []
    return [c for c in chunks if isinstance(c, dict) and c.get("text")]


def search_corpus(
    root: Path,
    studio_config: dict[str, Any],
    query: str,
    *,
    top_k: int | None = None,
) -> list[RagChunk]:
    query = (query or "").strip()
    if not query:
        return []

    k = top_k if top_k is not None else rag_top_k(studio_config)
    indexed = _load_index(root, studio_config)
    if not indexed:
        return []

    scored: list[RagChunk] = []
    for item in indexed:
        text = str(item.get("text") or "")
        score = _score_query(query, text)
        if score <= 0:
            continue
        scored.append(
            RagChunk(
                chunk_id=str(item.get("chunk_id") or item.get("source") or ""),
                source=str(item.get("source") or ""),
                text=text,
                score=round(score, 4),
            )
        )

    scored.sort(key=lambda c: (-c.score, c.source, c.chunk_id))
    return scored[:k]


def format_rag_context(chunks: list[RagChunk]) -> str:
    if not chunks:
        return ""
    lines = ["【ユーザーコンテキスト（関連する過去の思考）】"]
    for chunk in chunks:
        lines.append(f"--- chunk: {chunk.source} (score: {chunk.score:.2f}) ---")
        lines.append(chunk.text)
    return "\n".join(lines)


def resolve_rag_context(
    root: Path,
    studio_config: dict[str, Any],
    query: str,
    *,
    no_user_context: bool = False,
    no_user_context_rag: bool = False,
) -> RagResolution:
    enabled = session_rag_enabled(
        studio_config,
        no_user_context=no_user_context,
        no_user_context_rag=no_user_context_rag,
    )
    if not enabled:
        return RagResolution(enabled=False, text=None, chunks=())

    chunks = search_corpus(root, studio_config, query)
    if not chunks:
        return RagResolution(enabled=True, text=None, chunks=())

    text = format_rag_context(chunks)
    return RagResolution(enabled=True, text=text, chunks=tuple(chunks))


def chunks_to_log(chunks: tuple[RagChunk, ...]) -> list[dict[str, Any]]:
    return [
        {"chunk_id": c.chunk_id, "source": c.source, "score": c.score}
        for c in chunks
    ]
