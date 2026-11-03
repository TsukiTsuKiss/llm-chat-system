from studio.errors import detect_api_error, handle_api_error


def test_tool_call_error_is_detected_and_retried():
    message = "APIError: Tool choice is none, but model called a tool"
    code = detect_api_error(message)
    assert code == "tool_call"
    assert handle_api_error(code, attempt=0, max_retries=3, retry_delay=0) is True
    assert handle_api_error(code, attempt=2, max_retries=3, retry_delay=0) is False


def test_existing_error_codes_are_unchanged():
    assert detect_api_error("Error code: 429 - rate limit") == "429"
    assert detect_api_error("Connection timeout") == "504"
    assert detect_api_error("something else") is None


def _invoke(monkeypatch, replies):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from studio.assistants import invoke_llm_step
    from studio.history import ConversationHistory

    calls = iter(replies)
    monkeypatch.setattr(
        "studio.assistants.build_llm",
        lambda *a, **k: RunnableLambda(lambda _: AIMessage(content=next(calls))),
    )
    return invoke_llm_step(
        assistant_name="Fake",
        assistant_cfg={},
        model="m",
        system_prompt="s",
        user_message="u",
        history=ConversationHistory(),
        temperature=None,
        stream=False,
        costs={"default": {"input": 0.0, "output": 0.0}},
    )


def test_empty_response_is_retried(monkeypatch):
    assert _invoke(monkeypatch, ["", "ok"]).text == "ok"


def test_empty_response_after_all_retries_raises(monkeypatch):
    import pytest

    from studio.assistants import EmptyResponseError

    with pytest.raises(EmptyResponseError):
        _invoke(monkeypatch, ["", "", ""])


def test_anthropic_gets_larger_max_tokens(monkeypatch):
    import sys
    import types

    from studio.assistants import build_llm

    seen = {}

    class ChatAnthropic:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    module = types.ModuleType("fake_anthropic_module")
    module.ChatAnthropic = ChatAnthropic
    monkeypatch.setitem(sys.modules, "fake_anthropic_module", module)
    build_llm({"module": "fake_anthropic_module", "class": "ChatAnthropic"}, "claude-x", None)
    assert seen["max_tokens"] == 8192
