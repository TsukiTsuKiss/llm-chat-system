"""Phase 6 user context RAG tests (design.md Appendix D.10)."""

from __future__ import annotations

import json
from pathlib import Path

from studio.assistants import MockAssistant
from studio.engine import SessionEngine, collect_events
from studio.loader import load_session_context
from studio.prompts import build_system_prompt
from studio.user_context_rag import (
    RagChunk,
    format_rag_context,
    reindex_corpus,
    resolve_rag_context,
    search_corpus,
)


def _write_rag_config(studio_root: Path, *, enabled: bool = True) -> dict:
    config = {
        "user_context": {
            "enabled": True,
            "path": "user_context/my_context.md",
            "rag": {
                "enabled": enabled,
                "corpus_dir": "user_context/corpus",
                "index_dir": "user_context/index",
                "top_k": 3,
            },
        }
    }
    studio_root.joinpath("studio_config.json").write_text(
        json.dumps(config, ensure_ascii=False),
        encoding="utf-8",
    )
    return config


def test_reindex_and_search_corpus(studio_root: Path) -> None:
    corpus = studio_root / "user_context" / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "loader_notes.md").write_text(
        "## loader\n\nE204 mock 対応と read_attachment_files の再帰展開。\n",
        encoding="utf-8",
    )
    (corpus / "parity_notes.md").write_text(
        "## parity\n\nPhase 5 parity テストと schema 検証。\n",
        encoding="utf-8",
    )
    config = _write_rag_config(studio_root)

    result = reindex_corpus(studio_root, config)
    assert result.ok
    assert result.chunk_count == 2

    hits = search_corpus(studio_root, config, "loader E204 mock")
    assert hits
    assert hits[0].source == "loader_notes.md"
    assert hits[0].score > 0


def test_format_rag_context_includes_header() -> None:
    from studio.user_context_rag import RagChunk

    text = format_rag_context(
        [RagChunk("loader_notes.md#0", "loader_notes.md", "E204 mock", 0.75)]
    )
    assert "【ユーザーコンテキスト（関連する過去の思考）】" in text
    assert "loader_notes.md (score: 0.75)" in text
    assert "E204 mock" in text


def test_build_system_prompt_injects_rag_after_user_context() -> None:
    talent = {"system_prompt": "SP"}
    org = {"mission": "M"}
    prompt = build_system_prompt(
        talent,
        org,
        "solo",
        "bot",
        user_context_text="コア定義",
        user_context_rag_text=format_rag_context(
            [RagChunk("x#0", "x.md", "関連メモ", 0.5)]
        ),
    )
    assert prompt.index("【ユーザーコンテキスト】") < prompt.index(
        "【ユーザーコンテキスト（関連する過去の思考）】"
    )
    assert "関連メモ" in prompt


def test_resolve_rag_disabled_by_default(studio_root: Path) -> None:
    resolution = resolve_rag_context(studio_root, {"user_context": {"enabled": True}}, "query")
    assert not resolution.enabled
    assert resolution.text is None


def test_no_user_context_rag_flag(studio_root: Path) -> None:
    corpus = studio_root / "user_context" / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "notes.md").write_text("## topic\n\nkeyword alpha\n", encoding="utf-8")
    config = _write_rag_config(studio_root, enabled=True)
    reindex_corpus(studio_root, config)

    resolution = resolve_rag_context(
        studio_root,
        config,
        "keyword alpha",
        no_user_context_rag=True,
    )
    assert not resolution.enabled


def test_session_logs_context_chunks(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    corpus = uc_dir / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ctx\n", encoding="utf-8")
    (corpus / "notes.md").write_text("## rag topic\n\nloader parity schema\n", encoding="utf-8")
    config = _write_rag_config(studio_root, enabled=True)
    reindex_corpus(studio_root, config)

    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "loader parity", stream=False)
    log_path = engine.state.logger.log_path  # type: ignore[union-attr]
    lines = log_path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    assert meta["generation"]["user_context_rag"] is True

    user_input = next(json.loads(line) for line in lines if '"type": "user_input"' in line)
    assert user_input.get("context_chunks")
    assert user_input["context_chunks"][0]["source"] == "notes.md"


def test_session_meta_user_context_rag_false_with_cli_flag(studio_root: Path) -> None:
    uc_dir = studio_root / "user_context"
    corpus = uc_dir / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (uc_dir / "my_context.md").write_text("ctx\n", encoding="utf-8")
    (corpus / "notes.md").write_text("## rag\n\nkeyword\n", encoding="utf-8")
    config = _write_rag_config(studio_root, enabled=True)
    reindex_corpus(studio_root, config)

    MockAssistant.reset()
    ctx = load_session_context("solo", studio_root)
    engine = SessionEngine(ctx)
    collect_events(engine, "keyword", stream=False, no_user_context_rag=True)
    log_path = engine.state.logger.log_path  # type: ignore[union-attr]
    meta = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert meta["generation"]["user_context_rag"] is False
