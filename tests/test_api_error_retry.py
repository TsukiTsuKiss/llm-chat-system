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


def test_sakura_skips_web_search_before_calling_api(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from studio.assistants import WEB_SEARCH_SKIP_NOTE, invoke_llm_step
    from studio.history import ConversationHistory

    seen: list[bool] = []

    def fake_build(*args, **kwargs):
        seen.append(bool(args[3] if len(args) > 3 else kwargs.get("web_search")))
        return RunnableLambda(lambda _: AIMessage(content="了解です"))

    monkeypatch.setattr("studio.assistants.build_llm", fake_build)
    result = invoke_llm_step(
        assistant_name="SakuraAI",
        assistant_cfg={"class": "ChatOpenAI", "web_search": False},
        model="gpt-oss-120b",
        system_prompt="s",
        user_message="u",
        history=ConversationHistory(),
        temperature=None,
        stream=False,
        costs={"default": {"input": 0.0, "output": 0.0}},
        web_search=True,
    )
    assert seen == [False]
    assert result.text == "了解です"
    assert result.notice == WEB_SEARCH_SKIP_NOTE


def test_web_search_unsupported_is_detected():
    message = "BadRequestError: Error code: 400 - {'error': {'message': 'tool type web_search not supported'}}"
    assert detect_api_error(message) == "web_search_unsupported"


def test_web_search_unsupported_retries_without_tool(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from studio.assistants import WEB_SEARCH_SKIP_NOTE, invoke_llm_step
    from studio.history import ConversationHistory

    seen: list[bool] = []

    def fake_build(*args, **kwargs):
        web_search = bool(args[3] if len(args) > 3 else kwargs.get("web_search"))
        seen.append(web_search)
        if web_search:
            raise RuntimeError("Error code: 400 - {'error': {'message': 'tool type web_search not supported'}}")
        return RunnableLambda(lambda _: AIMessage(content="手元の資料ではこうです"))

    monkeypatch.setattr("studio.assistants.build_llm", fake_build)
    monkeypatch.setattr(
        "studio.assistants.web_search_tool_for",
        lambda *a, **k: {"type": "web_search"},
    )
    result = invoke_llm_step(
        assistant_name="SakuraAI",
        assistant_cfg={"class": "ChatOpenAI"},
        model="gpt-oss-120b",
        system_prompt="s",
        user_message="u",
        history=ConversationHistory(),
        temperature=None,
        stream=False,
        costs={"default": {"input": 0.0, "output": 0.0}},
        web_search=True,
    )
    assert seen == [True, False]
    assert result.text == "手元の資料ではこうです"
    assert result.notice == WEB_SEARCH_SKIP_NOTE


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
