from __future__ import annotations

import time
from langchain_core.messages import AIMessage

STREAM_PUNCT_CHARS_DEFAULT = "、。！？）」』】〉》〕］｝\n"


def _extract_text_from_chunk(chunk):
    """LangChainのストリームチャンクからテキストを取り出す。"""
    if chunk is None:
        return ""

    content = getattr(chunk, "content", chunk)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            else:
                text = getattr(part, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)

    return str(content)


def _render_stream_text(text, char_by_char=False, char_delay_ms=0.0):
    """ストリームテキストを表示モードに応じて描画する。"""
    if not text:
        return

    if not char_by_char:
        print(text, end="", flush=True)
        return

    delay_seconds = max(0.0, char_delay_ms) / 1000.0
    for ch in text:
        print(ch, end="", flush=True)
        if delay_seconds > 0:
            time.sleep(delay_seconds)


def _render_char_punct_stream_text(
    text,
    char_delay_ms=0.0,
    punct_pause_ms=220.0,
    punctuations=STREAM_PUNCT_CHARS_DEFAULT,
):
    """文字単位で滑らか表示しつつ、句読点でのみ追加ポーズを入れる。"""
    if not text:
        return

    base_delay = max(0.0, char_delay_ms) / 1000.0
    punct_delay = max(0.0, punct_pause_ms) / 1000.0
    punctuations = punctuations or STREAM_PUNCT_CHARS_DEFAULT

    for ch in text:
        print(ch, end="", flush=True)
        if base_delay > 0:
            time.sleep(base_delay)
        if ch in punctuations and punct_delay > 0:
            time.sleep(punct_delay)


def _render_buffered_stream_text(
    buffer,
    render_mode="batch",
    batch_chars=12,
    batch_delay_ms=50.0,
    punctuations=STREAM_PUNCT_CHARS_DEFAULT,
    force=False,
):
    """バッファ表示モード（batch/punct）を描画し、残バッファを返す。"""
    if not buffer:
        return ""

    delay_seconds = max(0.0, batch_delay_ms) / 1000.0
    safe_batch_chars = max(1, int(batch_chars))
    punctuations = punctuations or STREAM_PUNCT_CHARS_DEFAULT

    if render_mode == "batch":
        while buffer:
            if len(buffer) < safe_batch_chars and not force:
                break
            out = buffer[:safe_batch_chars] if len(buffer) >= safe_batch_chars else buffer
            buffer = buffer[len(out) :]
            print(out, end="", flush=True)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
        return buffer

    if render_mode == "punct":
        while buffer:
            flush_at = -1
            for p in punctuations:
                pos = buffer.rfind(p)
                if pos > flush_at:
                    flush_at = pos

            if flush_at >= 0:
                out = buffer[: flush_at + 1]
                buffer = buffer[flush_at + 1 :]
            elif len(buffer) >= safe_batch_chars:
                out = buffer[:safe_batch_chars]
                buffer = buffer[safe_batch_chars:]
            elif force:
                out = buffer
                buffer = ""
            else:
                break

            print(out, end="", flush=True)
            if delay_seconds > 0:
                time.sleep(delay_seconds)

    return buffer


def invoke_with_optional_stream(
    conversation,
    user_input,
    stream_mode,
    label,
    render_mode="chunk",
    char_by_char=False,
    char_delay_ms=0.0,
    punct_pause_ms=220.0,
    punct_chars=STREAM_PUNCT_CHARS_DEFAULT,
    batch_chars=12,
    batch_delay_ms=50.0,
):
    """必要に応じてストリーム表示しながら応答を取得する。"""
    if not stream_mode:
        response = conversation.invoke({"input": user_input})
        return response, False

    print(f"\n{label}")
    collected_parts = []
    pending_buffer = ""

    effective_mode = render_mode
    if char_by_char:
        effective_mode = "char"

    try:
        for chunk in conversation.stream({"input": user_input}):
            text_chunk = _extract_text_from_chunk(chunk)
            if text_chunk:
                if effective_mode == "chunk":
                    _render_stream_text(text_chunk, char_by_char=False, char_delay_ms=0.0)
                elif effective_mode == "char":
                    _render_stream_text(text_chunk, char_by_char=True, char_delay_ms=char_delay_ms)
                elif effective_mode == "char-punct":
                    _render_char_punct_stream_text(
                        text_chunk,
                        char_delay_ms=char_delay_ms,
                        punct_pause_ms=punct_pause_ms,
                        punctuations=punct_chars,
                    )
                else:
                    pending_buffer += text_chunk
                    pending_buffer = _render_buffered_stream_text(
                        pending_buffer,
                        render_mode=effective_mode,
                        batch_chars=batch_chars,
                        batch_delay_ms=batch_delay_ms,
                        punctuations=punct_chars,
                        force=False,
                    )
                collected_parts.append(text_chunk)

        if effective_mode in ["batch", "punct"] and pending_buffer:
            _render_buffered_stream_text(
                pending_buffer,
                render_mode=effective_mode,
                batch_chars=batch_chars,
                batch_delay_ms=batch_delay_ms,
                punctuations=punct_chars,
                force=True,
            )

        print()
        return AIMessage(content="".join(collected_parts)), True
    except Exception as stream_error:
        print(f"\n[WARNING] ストリーム出力に失敗したため通常出力にフォールバックします: {stream_error}")
        response = conversation.invoke({"input": user_input})
        return response, False


def get_post_response_wait_seconds(args):
    """実行時間表示の直前に入れる待機時間（秒）を算出する。"""
    if not getattr(args, "stream", False):
        return 0.0

    explicit_ms = float(getattr(args, "post_response_wait_ms", -1.0))
    if explicit_ms >= 0:
        return explicit_ms / 1000.0

    mode = getattr(args, "stream_render_mode", "chunk")
    if mode == "char-punct":
        base_ms = max(0.0, float(getattr(args, "stream_punct_pause_ms", 0.0)))
        return (base_ms * 2.0) / 1000.0 if base_ms > 0 else 0.0
    if mode == "punct":
        base_ms = max(0.0, float(getattr(args, "stream_batch_delay_ms", 0.0)))
        return (base_ms * 2.0) / 1000.0 if base_ms > 0 else 0.0
    if mode == "batch":
        base_ms = max(0.0, float(getattr(args, "stream_batch_delay_ms", 0.0)))
        return base_ms / 1000.0 if base_ms > 0 else 0.0
    if mode == "char":
        base_ms = max(0.0, float(getattr(args, "stream_char_delay_ms", 0.0)))
        return (base_ms * 4.0) / 1000.0 if base_ms > 0 else 0.0
    return 0.0


def render_status_text(
    text,
    stream_mode=False,
    render_mode="chunk",
    char_by_char=False,
    char_delay_ms=0.0,
    punct_pause_ms=220.0,
    punct_chars=STREAM_PUNCT_CHARS_DEFAULT,
    batch_chars=12,
    batch_delay_ms=50.0,
    leading_newline=True,
):
    """LLM本文以外の短いステータスメッセージを表示する。"""
    if leading_newline:
        print()

    if not stream_mode:
        print(text)
        return

    effective_mode = render_mode
    if char_by_char:
        effective_mode = "char"

    if effective_mode == "chunk":
        _render_stream_text(text, char_by_char=False, char_delay_ms=0.0)
    elif effective_mode == "char":
        _render_stream_text(text, char_by_char=True, char_delay_ms=char_delay_ms)
    elif effective_mode == "char-punct":
        _render_char_punct_stream_text(
            text,
            char_delay_ms=char_delay_ms,
            punct_pause_ms=punct_pause_ms,
            punctuations=punct_chars,
        )
    else:
        _render_buffered_stream_text(
            text,
            render_mode=effective_mode,
            batch_chars=batch_chars,
            batch_delay_ms=batch_delay_ms,
            punctuations=punct_chars,
            force=True,
        )

    print()
