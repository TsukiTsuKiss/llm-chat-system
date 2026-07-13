"""Workflow slot binding resolution and validation (design.md 4.2 / 5.3)."""

from __future__ import annotations

from typing import Any

from studio.validation import StudioError, ValidationReport

DIRECT_SLOT = "_direct"


def resolve_slot_bindings(
    org: dict[str, Any],
    workflow_id: str,
    workflow: dict[str, Any],
) -> dict[str, list[str]]:
    """Resolve slot -> [talent_id, ...] without validation errors."""
    slots: dict[str, Any] = workflow.get("slots") or {}
    talent_ids: list[str] = list(org.get("talent_ids") or [])
    explicit = (org.get("workflow_bindings") or {}).get(workflow_id) or {}

    resolved: dict[str, list[str]] = {}
    if len(slots) == 1 and not explicit:
        slot_name = next(iter(slots))
        resolved[slot_name] = list(talent_ids)
        return resolved

    for slot_name in slots:
        if slot_name in explicit:
            resolved[slot_name] = list(explicit[slot_name])
        elif len(slots) == 1:
            resolved[slot_name] = list(talent_ids)
        else:
            resolved[slot_name] = []
    return resolved


def validate_workflow_bindings(
    org_id: str,
    org: dict[str, Any],
    workflow_id: str,
    workflow: dict[str, Any],
    report: ValidationReport,
) -> dict[str, list[str]]:
    slots: dict[str, Any] = workflow.get("slots") or {}
    talent_ids = set(org.get("talent_ids") or [])
    explicit = (org.get("workflow_bindings") or {}).get(workflow_id) or {}

    for wf_id, bindings in (org.get("workflow_bindings") or {}).items():
        for slot_name, ids in bindings.items():
            for tid in ids:
                if tid not in talent_ids:
                    report.add(
                        StudioError(
                            code="E205",
                            target=f"organizations/{org_id}",
                            message=(
                                f"workflow_bindings の '{tid}' が talent_ids に含まれていません"
                            ),
                        )
                    )

    resolved = resolve_slot_bindings(org, workflow_id, workflow)

    if len(slots) > 1 and not explicit:
        for slot_name in slots:
            report.add(
                StudioError(
                    code="E301",
                    target=f"workflow '{workflow_id}'",
                    message=f"スロット '{slot_name}' への割当がありません",
                    hint="workflow_bindings に追加してください",
                )
            )
        return resolved

    for slot_name, slot_def in slots.items():
        assigned = resolved.get(slot_name, [])
        count = slot_def.get("count", "1+")

        if not assigned:
            report.add(
                StudioError(
                    code="E301",
                    target=f"workflow '{workflow_id}'",
                    message=f"スロット '{slot_name}' への割当がありません",
                    hint="workflow_bindings に追加してください",
                )
            )
            continue

        if count == "1" and len(assigned) != 1:
            report.add(
                StudioError(
                    code="E302",
                    target=f"workflow '{workflow_id}'",
                    message=(
                        f"スロット '{slot_name}'（count \"1\"）に"
                        f"{len(assigned)}人が割り当てられています"
                    ),
                )
            )
        elif count == "1+" and len(assigned) < 1:
            report.add(
                StudioError(
                    code="E302",
                    target=f"workflow '{workflow_id}'",
                    message=f"スロット '{slot_name}'（count \"1+\"）に割当がありません",
                )
            )

    return resolved


def expand_step_to_talents(
    step: dict[str, Any],
    bindings: dict[str, list[str]],
) -> list[tuple[str, str]]:
    """Expand a workflow step into (talent_id, action) pairs."""
    slot = step.get("slot", "")
    action = step.get("action", "")
    talent_ids = bindings.get(slot, [])
    return [(tid, action) for tid in talent_ids]


def build_direct_bindings(talent_ids: list[str]) -> dict[str, list[str]]:
    return {DIRECT_SLOT: list(talent_ids)}


def build_direct_workflow(talent_ids: list[str]) -> dict[str, Any]:
    steps = [{"slot": DIRECT_SLOT, "action": ""} for _ in talent_ids]
    return {
        "name": "直接送信",
        "slots": {DIRECT_SLOT: {"description": "直接送信", "count": "1+"}},
        "phases": [{"type": "serial", "steps": steps}],
    }


def org_has_human_talent(model_mapping: dict[str, dict[str, str]], talent_ids: list[str]) -> bool:
    for tid in talent_ids:
        if model_mapping.get(tid, {}).get("assistant") == "human":
            return True
    return False
