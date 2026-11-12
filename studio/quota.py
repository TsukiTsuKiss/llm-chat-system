"""プロバイダ無料枠のローカル集計。清書用の残りを会議で使い切らないようにする。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from studio.bindings import expand_step_to_talents


@dataclass(frozen=True)
class QuotaCheck:
    assistant: str
    used: int
    limit: int
    reserve: int
    expected: int
    remaining: int
    blocked: bool
    notice: str


def quota_spec(assistant_cfg: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(assistant_cfg, dict):
        return None
    raw = assistant_cfg.get("quota")
    if not isinstance(raw, dict):
        return None
    try:
        limit = int(raw.get("limit") or 0)
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    reserve = int(raw.get("reserve") or 0)
    max_session = int(raw.get("max_session") or 0)
    return {"limit": limit, "reserve": max(0, reserve), "max_session": max(0, max_session)}


def count_assistant_steps(
    root: Path,
    assistant_name: str,
    *,
    when: date | None = None,
) -> int:
    """sessions/<YYYYMMDD_HHMMSS>.jsonl の step を、その月だけ数える（他アプリの利用は見えない）。"""
    day = when or date.today()
    prefix = f"{day.year:04d}{day.month:02d}"
    sessions_dir = Path(root) / "sessions"
    if not sessions_dir.is_dir():
        return 0
    total = 0
    for path in sessions_dir.glob(f"{prefix}*.jsonl"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "step" and record.get("assistant") == assistant_name:
                total += 1
    return total


def expected_hits(
    workflow: dict[str, Any],
    bindings: dict[str, list[str]],
    mapping: dict[str, dict[str, Any]],
    assistant_name: str,
) -> int:
    hits = 0
    for phase in workflow.get("phases") or []:
        phase_hits = 0
        for step in phase.get("steps") or []:
            for talent_id, _action in expand_step_to_talents(step, bindings):
                if mapping.get(talent_id, {}).get("assistant") == assistant_name:
                    phase_hits += 1
        if phase.get("type") == "loop":
            try:
                repeats = int(phase.get("max_iterations") or 1)
            except (TypeError, ValueError):
                repeats = 1
            phase_hits *= max(1, repeats)
        hits += phase_hits
    return hits


def evaluate_quota(
    *,
    assistant: str,
    spec: dict[str, int],
    used: int,
    expected: int,
) -> QuotaCheck:
    limit = spec["limit"]
    reserve = spec["reserve"]
    max_session = spec["max_session"]
    remaining = max(0, limit - used)
    remaining_after = remaining - expected
    blocked = False
    reasons: list[str] = []
    if expected <= 0:
        notice = ""
        return QuotaCheck(assistant, used, limit, reserve, expected, remaining, False, notice)
    if remaining < expected:
        blocked = True
        reasons.append("この回の見込みが残り枠を超える")
    if max_session and expected > max_session:
        blocked = True
        reasons.append(
            f"1回 {expected} リクエストは会議向き。無料枠の清書用に、1回 {max_session} まで"
        )
    if expected > 1 and remaining_after < reserve:
        blocked = True
        reasons.append(f"清書用に {reserve} リクエスト残す")
    head = (
        f"{assistant} 無料枠（ローカル集計・今月）: {used}/{limit}、残り {remaining}。"
        f"この回の見込み {expected}。清書用に {reserve} 残す。"
    )
    if blocked:
        notice = head + " " + "。".join(reasons) + "。他のプロバイダで会議し、SakuraAI は清書・短い検証に使う。"
    else:
        notice = head
    return QuotaCheck(assistant, used, limit, reserve, expected, remaining, blocked, notice)


def checks_for_session(
    root: Path,
    assistants: dict[str, dict[str, Any]],
    workflow: dict[str, Any],
    bindings: dict[str, list[str]],
    mapping: dict[str, dict[str, Any]],
    *,
    when: date | None = None,
) -> list[QuotaCheck]:
    names = {str(entry.get("assistant") or "") for entry in mapping.values()}
    results: list[QuotaCheck] = []
    for name in sorted(names):
        spec = quota_spec(assistants.get(name))
        if spec is None:
            continue
        expected = expected_hits(workflow, bindings, mapping, name)
        if expected <= 0:
            continue
        used = count_assistant_steps(root, name, when=when)
        results.append(evaluate_quota(assistant=name, spec=spec, used=used, expected=expected))
    return results
