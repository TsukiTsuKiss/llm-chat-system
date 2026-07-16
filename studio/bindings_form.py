"""workflow_bindings form helpers (design.md §8.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio.config_store import list_configs, load_config


@dataclass(frozen=True)
class BindingSlotSpec:
    workflow_id: str
    workflow_name: str
    slot_name: str
    count: str
    description: str
    multi_slot: bool


def load_binding_slot_specs(root: Path) -> list[BindingSlotSpec]:
    specs: list[BindingSlotSpec] = []
    for workflow_id in list_configs("workflow", root):
        workflow = load_config("workflow", workflow_id, root)
        slots: dict[str, Any] = workflow.get("slots") or {}
        multi_slot = len(slots) > 1
        for slot_name, slot_def in slots.items():
            specs.append(
                BindingSlotSpec(
                    workflow_id=workflow_id,
                    workflow_name=str(workflow.get("name") or workflow_id),
                    slot_name=slot_name,
                    count=str(slot_def.get("count") or "1"),
                    description=str(slot_def.get("description") or ""),
                    multi_slot=multi_slot,
                )
            )
    return specs


def normalize_bindings_state(
    bindings: dict[str, Any] | None,
    slot_specs: list[BindingSlotSpec],
) -> dict[str, dict[str, list[str]]]:
    source = bindings or {}
    result: dict[str, dict[str, list[str]]] = {}
    for spec in slot_specs:
        wf_binding = source.get(spec.workflow_id) or {}
        raw = wf_binding.get(spec.slot_name, [])
        if isinstance(raw, str):
            assigned = [raw] if raw else []
        else:
            assigned = list(raw or [])
        result.setdefault(spec.workflow_id, {})[spec.slot_name] = assigned
    return result


def filter_assignments_to_talents(
    assignments: list[str] | str | None,
    talent_ids: list[str],
) -> list[str]:
    if isinstance(assignments, str):
        assignments = [assignments] if assignments else []
    talent_set = set(talent_ids or [])
    return [talent_id for talent_id in (assignments or []) if talent_id in talent_set]


def prune_bindings_state(
    state: dict[str, Any] | None,
    talent_ids: list[str],
    slot_specs: list[BindingSlotSpec],
) -> dict[str, dict[str, list[str]]]:
    talent_set = set(talent_ids or [])
    pruned: dict[str, dict[str, list[str]]] = {}
    for wf_id, slots in (state or {}).items():
        cleaned: dict[str, list[str]] = {}
        for slot_name, assigned in (slots or {}).items():
            filtered = [tid for tid in assigned if tid in talent_set]
            if filtered:
                cleaned[slot_name] = filtered
        if cleaned:
            pruned[wf_id] = cleaned
    return normalize_bindings_state(pruned, slot_specs)


def patch_bindings_slot(
    state: dict[str, Any] | None,
    workflow_id: str,
    slot_name: str,
    value: str | list[str] | None,
    *,
    count: str,
) -> dict[str, dict[str, list[str]]]:
    merged = {
        wf_id: {slot: list(ids) for slot, ids in slots.items()}
        for wf_id, slots in (state or {}).items()
    }
    if count == "1":
        assigned = [value] if value else []
    else:
        assigned = list(value or [])
    merged.setdefault(workflow_id, {})[slot_name] = assigned
    return merged


def build_bindings_payload(
    state: dict[str, Any] | None,
    talent_ids: list[str],
    workflows: dict[str, dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    talent_set = set(talent_ids or [])
    result: dict[str, dict[str, list[str]]] = {}
    source = state or {}

    for workflow_id, workflow in workflows.items():
        slots: dict[str, Any] = workflow.get("slots") or {}
        if not slots:
            continue
        wf_state = source.get(workflow_id) or {}
        cleaned: dict[str, list[str]] = {}
        for slot_name in slots:
            raw = wf_state.get(slot_name, [])
            if isinstance(raw, str):
                raw = [raw] if raw else []
            assigned = [tid for tid in (raw or []) if tid in talent_set]
            if assigned:
                cleaned[slot_name] = assigned

        if len(slots) > 1:
            result[workflow_id] = {slot: cleaned.get(slot, []) for slot in slots}
            continue

        slot_name = next(iter(slots))
        assigned = cleaned.get(slot_name, [])
        if assigned and set(assigned) != talent_set:
            result[workflow_id] = {slot_name: assigned}
    return result
