"""LLM / mock assistant invocation."""

from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate

from studio.errors import detect_api_error, handle_api_error, is_temperature_unsupported_error
from studio.history import ConversationHistory
from studio.logging import compute_cost, estimate_tokens


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

        marker = os.environ.get("STUDIO_MOCK_MARKER")
        if marker and ("集約" in action or "判断" in action or "終了条件" in action):
            text = f"MOCK:{talent_id}:step{step_number} {marker}了"
        elif os.environ.get("STUDIO_MOCK_JUDGE_EXIT") == "1" and "【判定】" in action:
            text = "【判定】終了\nMOCK: judge OK"
        elif os.environ.get("STUDIO_MOCK_EMIT_CODE") == "1":
            text = (
                f'MOCK:{talent_id}:step{step_number}\n'
                "ファイル名: hello.py\n```python\nprint('hello')\n```"
            )
        else:
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
            elif isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"):
                continue
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def build_llm(assistant_cfg: dict[str, Any], model: str, temperature: float | None):
    module = importlib.import_module(assistant_cfg["module"])
    cls = getattr(module, assistant_cfg["class"])
    kwargs: dict[str, Any] = {"model": model}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return cls(**kwargs)


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
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> InvokeResult:
    input_bundle = f"{system_prompt}\n{user_message}"
    attempt = 0
    effective_temperature = temperature
    temp_fallback_used = False

    while attempt < max_retries:
        try:
            llm = build_llm(assistant_cfg, model, effective_temperature)
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
                output_text = "".join(chunks)
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
            output_text = content_to_text(getattr(response, "content", response))
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
