"""Tests for assistant availability and mapping form (Phase 4d)."""

from __future__ import annotations

import pytest

from studio.assistant_availability import (
    assistant_dropdown_choices,
    is_assistant_available,
    model_dropdown_choices,
    required_api_keys,
    unavailable_reason,
)
from studio.mapping_form import (
    build_mapping_payload,
    merge_mapping_for_talents,
    ordered_talent_ids,
    patch_mapping_entry,
)


def test_required_api_keys_for_groq() -> None:
    keys = required_api_keys("Groq", {"class": "ChatGroq", "module": "langchain_groq"})
    assert keys == ("GROQ_API_KEY",)


def test_mock_and_human_need_no_api_keys() -> None:
    assert required_api_keys("mock", {}) == ()
    assert required_api_keys("human", {}) == ()
    assert is_assistant_available("mock", {})
    assert is_assistant_available("human", {})


def test_is_assistant_available_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = {"class": "ChatGroq", "module": "langchain_groq"}
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not is_assistant_available("Groq", cfg)
    assert "GROQ_API_KEY" in unavailable_reason("Groq", cfg)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    assert is_assistant_available("Groq", cfg)


def test_assistant_dropdown_marks_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assistants = {
        "Groq": {"class": "ChatGroq", "module": "langchain_groq", "models": ["a"]},
        "mock": {},
    }
    choices, selectable = assistant_dropdown_choices(assistants)
    labels = [label for label, _value in choices]
    assert any("Groq" in label and "APIキー未設定" in label for label in labels)
    assert "mock" in selectable
    assert "Groq" not in selectable


def test_model_dropdown_choices_from_catalog() -> None:
    assistants = {"ChatGPT": {"models": ["gpt-5.5", "gpt-5.4"]}}
    assert model_dropdown_choices("ChatGPT", assistants) == ["gpt-5.5", "gpt-5.4"]
    assert model_dropdown_choices("mock", assistants) == []


def test_merge_mapping_adds_defaults_for_new_talents() -> None:
    merged = merge_mapping_for_talents(
        ["alpha", "beta"],
        {"alpha": {"assistant": "mock", "model": ""}},
    )
    assert merged["alpha"]["assistant"] == "mock"
    assert merged["beta"]["assistant"] == "mock"


def test_build_mapping_payload_filters_to_selected_talents() -> None:
    payload = build_mapping_payload(
        ["solo_bot"],
        {
            "solo_bot": {"assistant": "mock"},
            "other": {"assistant": "Groq", "model": "x"},
        },
    )
    assert set(payload.keys()) == {"solo_bot"}


def test_patch_mapping_entry_updates_assistant_and_model() -> None:
    state = patch_mapping_entry({}, "a", assistant="Groq", model="llama")
    state = patch_mapping_entry(state, "a", model="gpt")
    assert state["a"]["assistant"] == "Groq"
    assert state["a"]["model"] == "gpt"


def test_ordered_talent_ids_preserves_config_order() -> None:
    order = ["hinata", "satsuki", "kaede"]
    selected = ["kaede", "hinata"]
    assert ordered_talent_ids(selected, order) == ["hinata", "kaede"]


def test_ordered_talent_ids_follows_choice_order() -> None:
    pool = ["alpha", "beta", "gamma", "hinata", "kaede", "satsuki"]
    selected = ["hinata", "alpha", "satsuki", "kaede"]
    assert ordered_talent_ids(selected, ["hinata", "satsuki", "kaede"], choice_order=pool) == [
        "alpha",
        "hinata",
        "kaede",
        "satsuki",
    ]


def test_ordered_talent_ids_appends_new_selections() -> None:
    assert ordered_talent_ids(["beta", "alpha"], ["alpha"]) == ["alpha", "beta"]
