"""設定駆動のクライアント生成（studio/assistants.py の build_llm / build_chain）のテスト。"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, ConfigDict

from studio import assistant_availability, assistants
from studio.history import ConversationHistory

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeGateway(BaseModel):
    """ChatOpperAI に似たクライアント: model_name / instructions を持ち、temperature は無く、知らない引数は黙って無視する。"""

    model_config = ConfigDict(extra="ignore")
    model_name: str = "default-model"
    instructions: str = "default instructions"
    api_key: str | None = None


class FakeOpenAILike(BaseModel):
    model: str = ""
    temperature: float | None = None
    base_url: str | None = None
    api_key: str | None = None
    max_retries: int | None = None


@pytest.fixture(autouse=True)
def fake_module(monkeypatch):
    module = types.ModuleType("fake_llm_module")
    module.FakeGateway = FakeGateway
    module.FakeOpenAILike = FakeOpenAILike
    monkeypatch.setitem(sys.modules, "fake_llm_module", module)


GATEWAY_CFG = {
    "module": "fake_llm_module", "class": "FakeGateway", "model_param": "model_name", "system_param": "instructions",
}
OPENAI_LIKE_CFG = {"module": "fake_llm_module", "class": "FakeOpenAILike"}


def test_model_and_system_param_come_from_config_and_unsupported_temperature_is_not_sent():
    llm = assistants.build_llm(GATEWAY_CFG, "vendor/model-x", 0.5, system_prompt="SYS")
    assert llm.model_name == "vendor/model-x" and llm.instructions == "SYS"
    assert assistants.supports_temperature(GATEWAY_CFG) is False
    assert assistants._reported_temperature(GATEWAY_CFG, 0.5) is None


def test_without_model_param_the_default_model_argument_is_used():
    llm = assistants.build_llm(OPENAI_LIKE_CFG, "m1", 0.2, system_prompt="ignored")
    assert llm.model == "m1" and llm.temperature == 0.2
    assert assistants._reported_temperature(OPENAI_LIKE_CFG, 0.2) == 0.2


def test_base_url_and_api_key_env_are_read_from_config(monkeypatch):
    cfg = {**OPENAI_LIKE_CFG, "base_url": "https://api.example.test/v1", "api_key_env": "FAKE_TEST_KEY"}
    monkeypatch.delenv("FAKE_TEST_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FAKE_TEST_KEY"):
        assistants.build_llm(cfg, "m", None)

    monkeypatch.setenv("FAKE_TEST_KEY", "secret-value")
    llm = assistants.build_llm(cfg, "m", None)
    assert llm.base_url == "https://api.example.test/v1" and llm.api_key == "secret-value"


def test_base_url_must_be_https():
    cfg = {**OPENAI_LIKE_CFG, "base_url": "http://insecure.example.test/v1"}
    with pytest.raises(ValueError, match="https://"):
        assistants.build_llm(cfg, "m", None)


def test_client_kwargs_only_apply_to_fields_the_class_has():
    assert assistants.build_llm(OPENAI_LIKE_CFG, "m", None, client_kwargs={"max_retries": 0}).max_retries == 0
    # temperature を持たないクライアントに、未知の引数を渡しても落ちず、渡されない
    assistants.build_llm(GATEWAY_CFG, "m", None, client_kwargs={"max_retries": 0})


def test_build_chain_omits_system_message_when_prompt_is_none():
    history = ConversationHistory()
    echo = RunnableLambda(lambda value: value.to_messages())
    with_system = assistants.build_chain("SYS", history, echo).invoke({"system_prompt": "SYS", "history": [], "input": "Q"})
    without = assistants.build_chain(None, history, echo).invoke({"system_prompt": "SYS", "history": [], "input": "Q"})
    assert isinstance(with_system[0], SystemMessage) and not any(isinstance(m, SystemMessage) for m in without)
    assert without[-1].content == "Q"


def test_api_key_env_in_config_drives_availability(monkeypatch):
    cfg = {**OPENAI_LIKE_CFG, "api_key_env": "FAKE_TEST_KEY"}
    assert assistant_availability.required_api_keys("X", cfg) == ("FAKE_TEST_KEY",)
    monkeypatch.delenv("FAKE_TEST_KEY", raising=False)
    assert assistant_availability.is_assistant_available("X", cfg) is False
    monkeypatch.setenv("FAKE_TEST_KEY", "v")
    assert assistant_availability.is_assistant_available("X", cfg) is True


def test_shipped_config_declares_opper_params_and_sakura_endpoint():
    config = json.loads((REPO_ROOT / "ai_assistants_config.json").read_text(encoding="utf-8"))
    assert config["Opper"]["model_param"] == "model_name" and config["Opper"]["system_param"] == "instructions"
    sakura = config["SakuraAI"]
    assert sakura["class"] == "ChatOpenAI" and sakura["api_key_env"] == "SAKURA_AI_API_KEY"
    assert "gpt-oss-120b" in sakura["models"]
    for name, entry in config.items():
        assert str(entry.get("base_url", "https://")).startswith("https://"), name
