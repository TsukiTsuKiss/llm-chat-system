"""通貨（円など）に対応した単価・費用の記録と表示（studio/logging.py, studio/display.py）のテスト。"""

from __future__ import annotations

from pathlib import Path

from studio import display
from studio.logging import (
    SessionLogger,
    StepMetrics,
    currency_of,
    format_money,
    load_model_costs,
    steps_from_jsonl,
)

HEADER = "date_updated,provider,model,input_cost_per_1k_tokens,output_cost_per_1k_tokens,currency,notes\n"


def _costs(tmp_path: Path) -> dict:
    (tmp_path / "model_costs.csv").write_text(
        HEADER
        + "2026-11-12,Sakura,jpy-model,0.015,0.075,JPY,x\n"
        + "2026-11-12,OpenAI,usd-model,0.001,0.002,USD,x\n"
        + "2026-11-12,OpenAI,blank-currency,0.001,0.002,,x\n",
        encoding="utf-8",
    )
    return load_model_costs(tmp_path)


def test_currency_comes_from_cost_table_and_defaults_to_usd(tmp_path: Path):
    costs = _costs(tmp_path)
    assert currency_of("jpy-model", costs) == "JPY"
    assert currency_of("usd-model", costs) == "USD"
    assert currency_of("blank-currency", costs) == "USD"
    assert currency_of("not-listed", costs) == "USD" and currency_of(None, costs) == "USD"
    assert costs["jpy-model"]["input"] == 0.015 / 1000


def test_format_money_uses_symbols():
    assert format_money(0.001, "USD") == "$0.001000"
    assert format_money(1.5, "JPY", 2) == "¥1.50"
    assert format_money(2, "EUR", 1) == "2.0 EUR"


def _step(model: str, cost: float) -> StepMetrics:
    return StepMetrics(
        talent_id="t", assistant="A", model=model, action="a", text="x", stream=False, elapsed=1.0,
        tokens_in=10, tokens_out=5, tokens_source="api", cost=cost,
    )


def test_logger_records_currency_and_splits_totals(tmp_path: Path):
    logger = SessionLogger(
        root=tmp_path, session_id="s", org_id="o", workflow=None, talents={}, models={}, generation={},
        costs=_costs(tmp_path),
    )
    logger.log_step(_step("usd-model", 0.5))
    logger.log_step(_step("jpy-model", 12.0))
    logger.log_step(_step("jpy-model", 3.0))
    end = logger.finish()

    assert end["total_cost"] == 0.5 and end["total_cost_other"] == {"JPY": 15.0}
    assert end["by_model"]["A/jpy-model"]["currency"] == "JPY" and "currency" not in end["by_model"]["A/usd-model"]

    steps = steps_from_jsonl(logger.log_path)
    assert [s.currency for s in steps] == ["USD", "JPY", "JPY"]
    assert "currency" not in logger.log_path.read_text(encoding="utf-8").splitlines()[0]  # USD の行には書かない


def test_usd_only_session_end_is_unchanged(tmp_path: Path):
    logger = SessionLogger(
        root=tmp_path, session_id="s", org_id="o", workflow=None, talents={}, models={}, generation={},
        costs=_costs(tmp_path),
    )
    logger.log_step(_step("usd-model", 0.25))
    end = logger.finish()
    assert "total_cost_other" not in end
    lines = display.format_session_end_lines(end)
    assert "total=$0.250000" in lines[0] and "cost (USD)" in lines[-1]


def test_display_shows_each_models_currency():
    payload = {"assistant": "A", "model": "m", "elapsed": 1.0, "tokens": {"in": 1, "out": 1, "source": "api"}, "cost": 1.5}
    assert display.format_step_metrics_line(payload).endswith("$1.500000")
    assert display.format_step_metrics_line({**payload, "currency": "JPY"}).endswith("¥1.500000")

    end = {
        "total_elapsed": 1, "total_cost": 0.5, "total_cost_other": {"JPY": 15.0},
        "by_model": {"A/jpy": {"requests": 1, "cost": 15.0, "currency": "JPY"}, "A/usd": {"requests": 1, "cost": 0.5}},
    }
    lines = display.format_session_end_lines(end)
    assert "total=$0.500000 + ¥15.000000" in lines[0]
    table = lines[-1]
    assert "| cost |" in table and "¥15.000000" in table and "$0.500000" in table
