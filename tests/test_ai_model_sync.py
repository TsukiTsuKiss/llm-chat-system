import json

from ai_model_sync import build_csv_rows, is_unavailable, new_candidates, remove_unavailable

CONFIG = {
    "Groq": {"module": "langchain_groq", "class": "ChatGroq", "models": ["a", "b", "c"]},
    "Together": {"module": "langchain_together", "class": "ChatTogether", "models": ["x"]},
}


def test_is_unavailable_only_for_missing_model_errors():
    assert is_unavailable("Error code: 404 - The model `m` does not exist")
    assert is_unavailable("Unable to access non-serverless model")
    assert not is_unavailable("Error code: 429 - rate limit")
    assert not is_unavailable("Connection timeout")


def test_new_candidates_skips_registered_and_non_chat():
    listed = ["a", "new-chat", "text-embedding-3", "whisper-large", "llama-guard-4", "z-model"]
    assert new_candidates(listed, ["a"]) == ["new-chat", "z-model"]


def test_remove_unavailable_keeps_other_models_and_original():
    updated = remove_unavailable(CONFIG, {"Groq": ["b"]})
    assert updated["Groq"]["models"] == ["a", "c"]
    assert CONFIG["Groq"]["models"] == ["a", "b", "c"]


def test_build_csv_rows_follows_json_and_keeps_unknown_rows():
    existing = [
        {"assistant_name": "Groq", "module": "m", "class": "c", "model": "old", "fast_model": "old2"},
        {"assistant_name": "Opper-Groq", "module": "o", "class": "O", "model": "g/1", "fast_model": "g/2"},
    ]
    rows = build_csv_rows(existing, CONFIG)
    assert rows == [
        ["Groq", "langchain_groq", "ChatGroq", "a", "b"],
        ["Opper-Groq", "o", "O", "g/1", "g/2"],
        ["Together", "langchain_together", "ChatTogether", "x", ""],
    ]


def test_config_is_json_serializable_after_removal():
    json.dumps(remove_unavailable(CONFIG, {"Together": ["x"]}))
