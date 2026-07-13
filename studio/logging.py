"""Session JSONL logging and cost estimation (design.md 7.1)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

MODEL_COSTS_FILE = "model_costs.csv"


def load_model_costs(root: Path) -> dict[str, dict[str, float]]:
    path = root / MODEL_COSTS_FILE
    costs: dict[str, dict[str, float]] = {
        "default": {"input": 0.001 / 1000, "output": 0.003 / 1000},
    }
    if not path.exists():
        return costs
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                model_name = row["model"]
                costs[model_name] = {
                    "input": float(row["input_cost_per_1k_tokens"]) / 1000,
                    "output": float(row["output_cost_per_1k_tokens"]) / 1000,
                }
    except (OSError, KeyError, ValueError):
        pass
    return costs


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    japanese_chars = len([c for c in text if ord(c) > 127])
    english_chars = len(text) - japanese_chars
    estimated = (japanese_chars / 2) + (english_chars / 4)
    return max(1, int(estimated))


def compute_cost(model: str | None, tokens_in: int, tokens_out: int, costs: dict[str, dict[str, float]]) -> float:
    if not model:
        return 0.0
    model_cost = costs.get(model, costs["default"])
    return tokens_in * model_cost["input"] + tokens_out * model_cost["output"]


@dataclass
class StepMetrics:
    talent_id: str
    assistant: str
    model: str | None
    action: str
    text: str
    stream: bool
    elapsed: float
    tokens_in: int
    tokens_out: int
    tokens_source: str
    cost: float
    phase_type: str | None = None

    def to_log_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "type": "step",
            "talent_id": self.talent_id,
            "assistant": self.assistant,
            "action": self.action,
            "text": self.text,
            "stream": self.stream,
            "elapsed": round(self.elapsed, 3),
            "tokens": {
                "in": self.tokens_in,
                "out": self.tokens_out,
                "source": self.tokens_source,
            },
            "cost": round(self.cost, 6),
        }
        if self.phase_type:
            record["phase_type"] = self.phase_type
        if self.model:
            record["model"] = self.model
            if self.elapsed > 0 and self.tokens_out > 0:
                record["metrics"] = {
                    "tokens_per_sec": round(self.tokens_out / self.elapsed, 1),
                }
        return record


@dataclass
class SessionLogger:
    root: Path
    session_id: str
    org_id: str
    workflow: str | None
    talents: dict[str, str]
    models: dict[str, dict[str, str]]
    generation: dict[str, Any]
    costs: dict[str, dict[str, float]] = field(default_factory=dict)
    steps: list[StepMetrics] = field(default_factory=list)
    total_elapsed: float = 0.0
    _started: bool = False

    @classmethod
    def create(
        cls,
        root: Path,
        org_id: str,
        workflow: str | None,
        talents: dict[str, dict[str, Any]],
        model_mapping: dict[str, dict[str, str]],
        generation: dict[str, Any],
    ) -> SessionLogger:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        display_names = {tid: t.get("name", tid) for tid, t in talents.items()}
        models = {
            tid: {"assistant": mapping["assistant"], **({"model": mapping["model"]} if mapping.get("model") else {})}
            for tid, mapping in model_mapping.items()
            if tid in talents
        }
        return cls(
            root=root,
            session_id=session_id,
            org_id=org_id,
            workflow=workflow,
            talents=display_names,
            models=models,
            generation=generation,
            costs=load_model_costs(root),
        )

    @property
    def log_path(self) -> Path:
        sessions_dir = self.root / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir / f"{self.session_id}.jsonl"

    def write_line(self, record: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def start(self) -> None:
        if self._started:
            return
        self.write_line(
            {
                "type": "session_meta",
                "organization": self.org_id,
                "workflow": self.workflow,
                "parent_session_id": None,
                "talents": self.talents,
                "models": self.models,
                "generation": self.generation,
            }
        )
        self._started = True

    def log_user_input(self, text: str, attachments: list[str] | None = None) -> None:
        record: dict[str, Any] = {"type": "user_input", "text": text}
        if attachments:
            record["attachments"] = attachments
        self.write_line(record)

    def log_step(self, metrics: StepMetrics) -> None:
        self.steps.append(metrics)
        self.write_line(metrics.to_log_record())

    def log_state_snapshot(self, state: dict[str, Any]) -> None:
        self.write_line({"type": "state_snapshot", "state": state})

    def build_by_model(self) -> dict[str, dict[str, Any]]:
        rollup: dict[str, dict[str, Any]] = {}
        for step in self.steps:
            if step.assistant in ("human", "mock"):
                continue
            key = f"{step.assistant}/{step.model}" if step.model else f"{step.assistant}/"
            bucket = rollup.setdefault(
                key,
                {
                    "requests": 0,
                    "elapsed_sum": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost": 0.0,
                    "stream_on": 0,
                    "stream_off": 0,
                },
            )
            bucket["requests"] += 1
            bucket["elapsed_sum"] += step.elapsed
            bucket["tokens_in"] += step.tokens_in
            bucket["tokens_out"] += step.tokens_out
            bucket["cost"] += step.cost
            if step.stream:
                bucket["stream_on"] += 1
            else:
                bucket["stream_off"] += 1
        for bucket in rollup.values():
            bucket["elapsed_sum"] = round(bucket["elapsed_sum"], 3)
            bucket["cost"] = round(bucket["cost"], 6)
        return rollup

    def finish(self) -> dict[str, Any]:
        total_cost = sum(s.cost for s in self.steps)
        end_record = {
            "type": "session_end",
            "total_elapsed": round(self.total_elapsed, 3),
            "total_cost": round(total_cost, 6),
            "by_model": self.build_by_model(),
            "log_path": str(self.log_path),
        }
        self.write_line(end_record)
        return end_record


def steps_from_jsonl(log_path: Path) -> list[StepMetrics]:
    """Rebuild step metrics from a session JSONL log (design.md 7.5(3))."""
    steps: list[StepMetrics] = []
    if not log_path.exists():
        return steps
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") != "step":
                continue
            tokens = record.get("tokens", {})
            steps.append(
                StepMetrics(
                    talent_id=record["talent_id"],
                    assistant=record.get("assistant", ""),
                    model=record.get("model"),
                    action=record.get("action", ""),
                    text=record.get("text", ""),
                    stream=record.get("stream", False),
                    elapsed=record.get("elapsed", 0.0),
                    tokens_in=tokens.get("in", 0),
                    tokens_out=tokens.get("out", 0),
                    tokens_source=tokens.get("source", "estimate"),
                    cost=record.get("cost", 0.0),
                    phase_type=record.get("phase_type"),
                )
            )
    return steps
