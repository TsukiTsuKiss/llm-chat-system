"""Tests for workflow_bindings form helpers (§8.4)."""

from __future__ import annotations

from pathlib import Path

from studio.bindings_form import (
    BindingSlotSpec,
    build_bindings_payload,
    filter_assignments_to_talents,
    normalize_bindings_state,
    patch_bindings_slot,
    prune_bindings_state,
)


def _meeting_specs() -> list[BindingSlotSpec]:
    return [
        BindingSlotSpec("meeting", "会議", "moderator", "1", "進行役", True),
        BindingSlotSpec("meeting", "会議", "member", "1+", "参加者", True),
    ]


def _discussion_spec() -> BindingSlotSpec:
    return BindingSlotSpec("discussion", "討議", "participant", "1+", "参加者", False)


def test_normalize_bindings_state_fills_missing_slots() -> None:
    specs = _meeting_specs()
    state = normalize_bindings_state({"meeting": {"moderator": ["hinata"]}}, specs)
    assert state["meeting"]["moderator"] == ["hinata"]
    assert state["meeting"]["member"] == []


def test_patch_bindings_slot_radio_and_checkbox() -> None:
    state = patch_bindings_slot({}, "meeting", "moderator", "hinata", count="1")
    state = patch_bindings_slot(state, "meeting", "member", ["satsuki", "kaede"], count="1+")
    assert state["meeting"]["moderator"] == ["hinata"]
    assert state["meeting"]["member"] == ["satsuki", "kaede"]


def test_prune_bindings_state_drops_unselected_talents() -> None:
    specs = _meeting_specs()
    state = {
        "meeting": {"moderator": ["hinata"], "member": ["satsuki", "removed"]},
    }
    pruned = prune_bindings_state(state, ["hinata", "satsuki"], specs)
    assert pruned["meeting"]["member"] == ["satsuki"]


def test_build_bindings_payload_multi_slot_keeps_empty_slots() -> None:
    workflows = {
        "meeting": {
            "slots": {
                "moderator": {"count": "1"},
                "member": {"count": "1+"},
            }
        }
    }
    payload = build_bindings_payload(
        {"meeting": {"moderator": ["hinata"]}},
        ["hinata", "satsuki"],
        workflows,
    )
    assert payload["meeting"]["moderator"] == ["hinata"]
    assert payload["meeting"]["member"] == []


def test_build_bindings_payload_single_slot_omits_full_roster() -> None:
    workflows = {"discussion": {"slots": {"participant": {"count": "1+"}}}}
    talent_ids = ["alpha", "beta"]
    full = build_bindings_payload(
        {"discussion": {"participant": talent_ids}},
        talent_ids,
        workflows,
    )
    assert "discussion" not in full
    partial = build_bindings_payload(
        {"discussion": {"participant": ["alpha"]}},
        talent_ids,
        workflows,
    )
    assert partial["discussion"]["participant"] == ["alpha"]


def test_filter_assignments_to_talents() -> None:
    assert filter_assignments_to_talents(["a", "b"], ["b"]) == ["b"]
    assert filter_assignments_to_talents("a", ["a", "c"]) == ["a"]


def test_load_binding_slot_specs_reads_repo_workflows() -> None:
    root = Path(__file__).resolve().parents[2]
    from studio.bindings_form import load_binding_slot_specs

    specs = load_binding_slot_specs(root)
    wf_ids = {spec.workflow_id for spec in specs}
    assert "meeting" in wf_ids
    assert "discussion" in wf_ids
    meeting = [s for s in specs if s.workflow_id == "meeting"]
    assert len(meeting) == 2
    assert meeting[0].multi_slot is True
    discussion = next(s for s in specs if s.workflow_id == "discussion")
    assert discussion.multi_slot is False
