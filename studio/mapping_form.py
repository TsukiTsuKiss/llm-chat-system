"""model_mapping form helpers (design.md §8.4)."""

from __future__ import annotations

from typing import Any

DEFAULT_MAPPING_ENTRY = {"assistant": "mock", "model": ""}


def normalize_mapping_entry(entry: dict[str, Any] | None) -> dict[str, str]:
    if not entry:
        return dict(DEFAULT_MAPPING_ENTRY)
    assistant = str(entry.get("assistant") or "mock").strip()
    model = entry.get("model")
    result = {"assistant": assistant}
    if model is not None and str(model).strip():
        result["model"] = str(model).strip()
    elif assistant not in ("mock", "human"):
        result["model"] = ""
    return result


def merge_mapping_for_talents(
    talent_ids: list[str],
    mapping: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    """Keep mapping entries for selected talents; add mock defaults for new ones."""
    merged: dict[str, dict[str, str]] = {}
    source = mapping or {}
    for talent_id in talent_ids:
        merged[talent_id] = normalize_mapping_entry(source.get(talent_id))
    return merged


def build_mapping_payload(
    talent_ids: list[str],
    mapping: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    if not talent_ids:
        return {}
    return merge_mapping_for_talents(talent_ids, mapping)


def ordered_talent_ids(
    selected: list[str],
    order: list[str] | None = None,
    *,
    choice_order: list[str] | None = None,
) -> list[str]:
    """Order selected talent IDs for Web UI display and save.

    When ``choice_order`` is given (CheckboxGroup choices / talents/ 一覧順),
    selected IDs follow that order — e.g. ``alpha`` before ``hinata``.
    Otherwise fall back to ``order`` (config.json) with unknown IDs appended.
    """
    selected_list = list(selected or [])
    if not selected_list:
        return []
    if choice_order:
        index = {name: i for i, name in enumerate(choice_order)}
        return sorted(selected_list, key=lambda name: index.get(name, len(choice_order)))
    selected_set = set(selected_list)
    result = [talent_id for talent_id in (order or []) if talent_id in selected_set]
    for talent_id in selected_list:
        if talent_id not in result:
            result.append(talent_id)
    return result


def patch_mapping_entry(
    mapping: dict[str, dict[str, Any]] | None,
    talent_id: str,
    *,
    assistant: str | None = None,
    model: str | None = None,
) -> dict[str, dict[str, str]]:
    state = {tid: normalize_mapping_entry(entry) for tid, entry in (mapping or {}).items()}
    entry = dict(state.get(talent_id, DEFAULT_MAPPING_ENTRY))
    if assistant is not None:
        entry["assistant"] = assistant.strip() or "mock"
        if entry["assistant"] in ("mock", "human"):
            entry.pop("model", None)
    if model is not None:
        text = model.strip()
        if text:
            entry["model"] = text
        else:
            entry.pop("model", None)
    state[talent_id] = normalize_mapping_entry(entry)
    return state
