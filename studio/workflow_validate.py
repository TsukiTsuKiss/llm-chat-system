"""Workflow structure validation (design.md 4.1 / 5.3 E303–E305)."""

from __future__ import annotations

from typing import Any

from studio.interrupt import workflow_has_interrupt_on as _workflow_has_interrupt_on
from studio.validation import StudioError, ValidationReport


def workflow_has_interrupt_on(workflow: dict[str, Any]) -> bool:
    return _workflow_has_interrupt_on(workflow)


def workflow_has_user_exit(workflow: dict[str, Any]) -> bool:
    for phase in workflow.get("phases") or []:
        if phase.get("type") == "loop":
            exit_cfg = phase.get("exit") or {}
            if exit_cfg.get("type") == "user":
                return True
    return False


def validate_workflow_structure(
    workflow_id: str,
    workflow: dict[str, Any],
    report: ValidationReport,
) -> None:
    slots = workflow.get("slots") or {}
    for phase in workflow.get("phases") or []:
        _validate_phase(workflow_id, workflow, slots, phase, report)


def _validate_phase(
    workflow_id: str,
    workflow: dict[str, Any],
    slots: dict[str, Any],
    phase: dict[str, Any],
    report: ValidationReport,
) -> None:
    phase_type = phase.get("type")
    if phase_type == "loop":
        exit_cfg = phase.get("exit") or {}
        exit_type = exit_cfg.get("type")
        if exit_type != "user" and not phase.get("max_iterations"):
            report.add(
                StudioError(
                    code="E303",
                    target=f"workflow '{workflow_id}'",
                    message="loop に max_iterations がありません",
                    hint='exit.type "user" 以外では必須',
                )
            )
        if exit_type == "judge":
            slot = exit_cfg.get("slot", "")
            if slot not in slots:
                report.add(
                    StudioError(
                        code="E304",
                        target=f"workflow '{workflow_id}'",
                        message=f"exit.judge の slot '{slot}' が slots に宣言されていません",
                    )
                )
        if exit_type == "marker":
            inner = phase.get("phases") or []
            if inner and inner[-1].get("type") == "parallel":
                report.add(
                    StudioError(
                        code="E305",
                        target=f"workflow '{workflow_id}'",
                        message='exit.type "marker" ではループ最終 phase を parallel にできません',
                    )
                )
        for inner in phase.get("phases") or []:
            _validate_phase(workflow_id, workflow, slots, inner, report)
