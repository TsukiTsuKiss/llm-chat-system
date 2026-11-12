from datetime import date
from pathlib import Path

from studio.quota import (
    count_assistant_steps,
    evaluate_quota,
    expected_hits,
    quota_spec,
)


SAKURA_SPEC = {"limit": 3000, "reserve": 80, "max_session": 2}


def test_quota_spec_ignores_missing_and_zero():
    assert quota_spec({}) is None
    assert quota_spec({"quota": {"limit": 0}}) is None
    assert quota_spec({"quota": {"limit": 3000, "reserve": 80, "max_session": 2}}) == SAKURA_SPEC


def test_expected_hits_counts_serial_sakura_only():
    workflow = {
        "phases": [
            {
                "type": "serial",
                "steps": [
                    {"slot": "planner", "action": "a"},
                    {"slot": "analyst", "action": "b"},
                    {"slot": "secretary", "action": "c"},
                ],
            }
        ]
    }
    bindings = {"planner": ["kazuma"], "analyst": ["mizuki"], "secretary": ["kanna"]}
    mapping = {
        "kazuma": {"assistant": "SakuraAI"},
        "mizuki": {"assistant": "Gemini"},
        "kanna": {"assistant": "SakuraAI"},
    }
    assert expected_hits(workflow, bindings, mapping, "SakuraAI") == 2
    assert expected_hits(workflow, bindings, mapping, "Gemini") == 1


def test_evaluate_quota_blocks_meetings_over_max_session():
    meeting = evaluate_quota(assistant="SakuraAI", spec=SAKURA_SPEC, used=10, expected=6)
    assert meeting.blocked is True
    assert "清書" in meeting.notice

    solo = evaluate_quota(assistant="SakuraAI", spec=SAKURA_SPEC, used=10, expected=1)
    assert solo.blocked is False
    assert "10/3000" in solo.notice


def test_evaluate_quota_keeps_reserve_for_multi_step():
    near = evaluate_quota(assistant="SakuraAI", spec=SAKURA_SPEC, used=2925, expected=2)
    assert near.blocked is True
    leftover = evaluate_quota(assistant="SakuraAI", spec=SAKURA_SPEC, used=2925, expected=1)
    assert leftover.blocked is False


def test_evaluate_quota_blocks_when_remaining_too_small():
    check = evaluate_quota(assistant="SakuraAI", spec=SAKURA_SPEC, used=2999, expected=2)
    assert check.blocked is True
    assert check.remaining == 1


def test_count_assistant_steps_this_month_only(tmp_path: Path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "20261113_010000.jsonl").write_text(
        '{"type":"step","assistant":"SakuraAI"}\n{"type":"step","assistant":"ChatGPT"}\n',
        encoding="utf-8",
    )
    (sessions / "20261001_010000.jsonl").write_text(
        '{"type":"step","assistant":"SakuraAI"}\n',
        encoding="utf-8",
    )
    assert count_assistant_steps(tmp_path, "SakuraAI", when=date(2026, 11, 1)) == 1
    assert count_assistant_steps(tmp_path, "SakuraAI", when=date(2026, 10, 1)) == 1
