"""LLM / mock assistant invocation."""

from __future__ import annotations

import importlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate

from studio.errors import detect_api_error, handle_api_error, is_temperature_unsupported_error
from studio.history import ConversationHistory
from studio.logging import compute_cost, estimate_tokens


def sanitize_model_output(text: str) -> str:
    """モデル出力に混ざる下書き・思考メモを除去する。"""
    raw = (text or "").strip()
    if not raw:
        return ""

    lower = raw.lower()
    suspicious = (
        lower.startswith("thought")
        or "\nthought\n" in lower
        or "文字数計算" in raw
        or "ルール確認" in raw
    )
    if not suspicious:
        return raw

    # 末尾に「出力する。」以降の最終本文を置くパターンを優先して採用する。
    for marker in ("出力する。", "出力する"):
        if marker in raw:
            tail = raw.split(marker, 1)[1].strip()
            if tail:
                return tail

    # フォールバック: 明らかな内部メモ見出し行を落として再構成する。
    meta_prefixes = (
        "thought",
        "analysis",
        "得られたニュース事実",
        "今回の発言のまとめ",
        "文字数チェック",
        "文章の下書き",
        "文字数計算",
        "ルール確認",
    )
    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if any(stripped.lower().startswith(prefix) for prefix in meta_prefixes):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned or raw


class MockTemperatureError(RuntimeError):
    """Injected once when STUDIO_MOCK_INJECT_TEMP_ERROR=1."""


@dataclass
class InvokeResult:
    text: str
    elapsed: float
    tokens_in: int
    tokens_out: int
    tokens_source: str
    cost: float
    stream: bool


class MockAssistant:
    _temp_error_used: bool = False

    @classmethod
    def reset(cls) -> None:
        cls._temp_error_used = False

    @classmethod
    def invoke(
        cls,
        talent_id: str,
        step_number: int,
        *,
        stream: bool,
        on_chunk: Callable[[str], None] | None = None,
        action: str = "",
    ) -> InvokeResult:
        if os.environ.get("STUDIO_MOCK_INJECT_TEMP_ERROR") == "1" and not cls._temp_error_used:
            cls._temp_error_used = True
            raise MockTemperatureError("temperature is not supported for mock model")

        text: str | None = None
        loop_marker = os.environ.get("STUDIO_MOCK_MARKER")
        if loop_marker and ("集約" in action or "判断" in action or "終了条件" in action):
            text = f"MOCK:{talent_id}:step{step_number} {loop_marker}了"
        interrupt_marker = os.environ.get("STUDIO_MOCK_INTERRUPT")
        if text is None and interrupt_marker and (
            os.environ.get("STUDIO_MOCK_INTERRUPT_ALWAYS") == "1"
            or "確認" in action
            or "質問" in action
        ):
            text = f"MOCK:{talent_id}:step{step_number} ご確認ください {interrupt_marker}"
        elif text is None and os.environ.get("STUDIO_MOCK_JUDGE_EXIT") == "1" and "【判定】" in action:
            text = "【判定】終了\nMOCK: judge OK"
        elif text is None and os.environ.get("STUDIO_MOCK_EMIT_CODE") == "1":
            text = (
                f'MOCK:{talent_id}:step{step_number}\n'
                "ファイル名: hello.py\n```python\nprint('hello')\n```"
            )
        elif text is None:
            text = f"MOCK:{talent_id}:step{step_number}"
        if stream and on_chunk:
            for ch in text:
                on_chunk(ch)
        return InvokeResult(
            text=text,
            elapsed=0.0,
            tokens_in=0,
            tokens_out=0,
            tokens_source="none",
            cost=0.0,
            stream=stream,
        )


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict):
                continue
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


logger = logging.getLogger(__name__)

# langchain_groq 0.3.8 の bind_tools は dict ツールを変換できないため bind(tools=...) を使う
WEB_SEARCH_TOOLS: dict[str, dict[str, Any]] = {
    "ChatGroq": {"type": "browser_search"},
    "ChatOpenAI": {"type": "web_search"},
    "ChatXAI": {"type": "web_search"},
    "ChatAnthropic": {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
    "ChatGoogleGenerativeAI": {"google_search": {}},
}

# Anthropic は既定 1024 だと thinking/検索で使い切り本文が途切れる
WEB_SEARCH_EXTRA_KWARGS: dict[str, dict[str, Any]] = {
    "ChatAnthropic": {"max_tokens": 4096},
}


def build_llm(
    assistant_cfg: dict[str, Any],
    model: str,
    temperature: float | None,
    web_search: bool = False,
):
    module = importlib.import_module(assistant_cfg["module"])
    cls = getattr(module, assistant_cfg["class"])
    kwargs: dict[str, Any] = {"model": model}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if web_search:
        kwargs.update(WEB_SEARCH_EXTRA_KWARGS.get(assistant_cfg["class"], {}))
    llm = cls(**kwargs)
    if web_search:
        tool = WEB_SEARCH_TOOLS.get(assistant_cfg["class"])
        if tool is None:
            logger.warning("web_search は %s 未対応のため無視します", assistant_cfg["class"])
        else:
            llm = llm.bind(tools=[tool])
    return llm


def build_chain(system_prompt: str, history: ConversationHistory, llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template("{system_prompt}"),
            MessagesPlaceholder(variable_name="history"),
            HumanMessagePromptTemplate.from_template("{input}"),
        ]
    )
    return prompt | llm


def extract_usage(response: Any, input_text: str, output_text: str) -> tuple[int, int, str]:
    meta = getattr(response, "response_metadata", None) or {}
    usage = meta.get("token_usage") or meta.get("usage") or {}
    if not usage:
        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta:
            usage = usage_meta

    prompt_tokens = usage.get("input_tokens") or usage.get("prompt_tokens")
    completion_tokens = usage.get("output_tokens") or usage.get("completion_tokens")
    if prompt_tokens is not None and completion_tokens is not None:
        return int(prompt_tokens), int(completion_tokens), "api"

    return estimate_tokens(input_text), estimate_tokens(output_text), "estimate"


def invoke_llm_step(
    *,
    assistant_name: str,
    assistant_cfg: dict[str, Any],
    model: str,
    system_prompt: str,
    user_message: str,
    history: ConversationHistory,
    temperature: float | None,
    stream: bool,
    costs: dict[str, dict[str, float]],
    on_chunk: Callable[[str], None] | None = None,
    web_search: bool = False,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> InvokeResult:
    input_bundle = f"{system_prompt}\n{user_message}"
    attempt = 0
    effective_temperature = temperature
    temp_fallback_used = False

    while attempt < max_retries:
        try:
            llm = build_llm(assistant_cfg, model, effective_temperature, web_search)
            chain = build_chain(system_prompt, history, llm)
            messages = history.get_messages()
            payload = {"system_prompt": system_prompt, "history": messages, "input": user_message}

            start = time.perf_counter()
            if stream and on_chunk is not None:
                chunks: list[str] = []
                for chunk in chain.stream(payload):
                    text = content_to_text(getattr(chunk, "content", chunk))
                    if text:
                        chunks.append(text)
                        on_chunk(text)
                output_text = sanitize_model_output("".join(chunks))
                elapsed = time.perf_counter() - start
                tokens_in, tokens_out, source = estimate_tokens(input_bundle), estimate_tokens(output_text), "estimate"
                cost = compute_cost(model, tokens_in, tokens_out, costs)
                history.add_message(HumanMessage(content=user_message))
                history.add_message(AIMessage(content=output_text))
                return InvokeResult(
                    text=output_text,
                    elapsed=elapsed,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    tokens_source=source,
                    cost=cost,
                    stream=True,
                )

            response = chain.invoke(payload)
            elapsed = time.perf_counter() - start
            output_text = sanitize_model_output(content_to_text(getattr(response, "content", response)))
            tokens_in, tokens_out, source = extract_usage(response, input_bundle, output_text)
            cost = compute_cost(model, tokens_in, tokens_out, costs)
            history.add_message(HumanMessage(content=user_message))
            history.add_message(AIMessage(content=output_text))
            return InvokeResult(
                text=output_text,
                elapsed=elapsed,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                tokens_source=source,
                cost=cost,
                stream=False,
            )
        except MockTemperatureError:
            raise
        except Exception as exc:
            if (
                effective_temperature is not None
                and not temp_fallback_used
                and is_temperature_unsupported_error(exc)
            ):
                effective_temperature = None
                temp_fallback_used = True
                continue

            error_code = detect_api_error(str(exc))
            should_retry = handle_api_error(
                error_code,
                attempt,
                max_retries,
                retry_delay,
                reduce_history=history.reduce_history,
            )
            attempt += 1
            if not should_retry:
                raise
    raise RuntimeError("max retries exceeded")


def invoke_mock_step(
    talent_id: str,
    step_number: int,
    *,
    stream: bool,
    history: ConversationHistory,
    user_message: str,
    on_chunk: Callable[[str], None] | None = None,
    action: str = "",
) -> InvokeResult:
    for attempt in range(2):
        try:
            result = MockAssistant.invoke(talent_id, step_number, stream=stream, on_chunk=on_chunk, action=action)
            history.add_message(HumanMessage(content=user_message))
            history.add_message(AIMessage(content=result.text))
            return result
        except MockTemperatureError:
            if attempt == 0:
                continue
            raise
    raise RuntimeError("mock invoke failed")
