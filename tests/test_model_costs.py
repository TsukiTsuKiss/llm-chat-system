"""単価表（model_costs.csv）の単位の検査。列は 1K トークンあたりの米ドルで、100 万トークンあたりの値が混ざると 1000 倍ずれる。"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 1K トークンあたり。最も高い実在のモデルでも出力で 100 万トークンあたり 600 ドル（= 0.6）程度
MAX_INPUT_PER_1K = 0.5
MAX_OUTPUT_PER_1K = 1.0


def _rows() -> list[dict[str, str]]:
    with (REPO_ROOT / "model_costs.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_model_costs_are_per_1k_tokens():
    too_high = [
        f"{r['provider']}/{r['model']} ({r['input_cost_per_1k_tokens']} / {r['output_cost_per_1k_tokens']})"
        for r in _rows()
        if float(r["input_cost_per_1k_tokens"]) > MAX_INPUT_PER_1K
        or float(r["output_cost_per_1k_tokens"]) > MAX_OUTPUT_PER_1K
    ]
    assert not too_high, "100 万トークンあたりの値が混ざっている可能性があります: " + ", ".join(too_high)


def test_model_costs_have_default_row_and_valid_numbers():
    rows = _rows()
    assert any(r["model"] == "default" for r in rows)
    for r in rows:
        assert float(r["input_cost_per_1k_tokens"]) >= 0 and float(r["output_cost_per_1k_tokens"]) >= 0, r["model"]
