"""Workflow execution engine (Phase 1: direct send + serial)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from langchain_core.messages import AIMessage, HumanMessage

from studio.assistants import invoke_llm_step, invoke_mock_step
from studio.history import RoleHistories
from studio.loader import SessionContext
from studio.logging import SessionLogger, StepMetrics
from studio.prompts import build_system_prompt, build_user_message
from studio.validation import StudioError, StudioValidationError

DIRECT_SLOT = "_direct"


@dataclass(frozen=True)
class EngineEvent:
    type: str
    payload: dict[str, Any]


@dataclass
class EngineState:
    ctx: SessionContext
    logger: SessionLogger
    histories: RoleHistories = field(default_factory=RoleHistories)
    step_number: int = 0
    stream: bool = True
    temperature: float | None = 0.7
    attachment_context: str = ""
    started: bool = False
    session_wall_start: float = 0.0


def resolve_direct_talents(ctx: SessionContext) -> list[str]:
    return list(ctx.org.get("talent_ids") or [])


def expand_direct_steps(ctx: SessionContext) -> list[tuple[str, str]]:
    return [(talent_id, "") for talent_id in resolve_direct_talents(ctx)]


class SessionEngine:
    def __init__(self, ctx: SessionContext) -> None:
        self.ctx = ctx
        self.state: EngineState | None = None

    def run_turn(
        self,
        user_text: str,
        *,
        attachment_context: str = "",
        stream: bool | None = None,
        temperature: float | None = None,
    ) -> Iterator[EngineEvent]:
        if self.ctx.workflow_id:
            raise StudioValidationError(
                [
                    StudioError(
                        code="E402",
                        target="workflow",
                        message=f"Phase 1 では workflow '{self.ctx.workflow_id}' は未実装です",
                        hint="--workflow を省略して直接送信モードを使ってください",
                    )
                ]
            )

        generation = self.ctx.studio_config
        use_stream = generation.get("stream", True) if stream is None else stream
        use_temperature = generation.get("temperature", 0.7) if temperature is None else temperature

        if self.state is None:
            talent_ids = resolve_direct_talents(self.ctx)
            logger = SessionLogger.create(
                self.ctx.root,
                self.ctx.org_id,
                workflow=None,
                talents={tid: self.ctx.talents[tid] for tid in talent_ids if tid in self.ctx.talents},
                model_mapping=self.ctx.model_mapping,
                generation={"stream": use_stream, "temperature": use_temperature},
            )
            self.state = EngineState(
                ctx=self.ctx,
                logger=logger,
                stream=use_stream,
                temperature=use_temperature,
                attachment_context=attachment_context,
                session_wall_start=time.perf_counter(),
            )
        elif attachment_context:
            self.state.attachment_context = attachment_context

        state = self.state
        assert state is not None

        if not state.started:
            state.logger.start()
            yield EngineEvent(
                "session_start",
                {
                    "session_id": state.logger.session_id,
                    "org": self.ctx.org_id,
                    "workflow": None,
                    "talents": state.logger.talents,
                },
            )
            state.started = True

        state.logger.log_user_input(user_text)
        yield EngineEvent("phase_start", {"phase_type": "serial", "iteration": None})

        prior: list[tuple[str, str]] = []
        for talent_id, action in expand_direct_steps(self.ctx):
            talent = self.ctx.talents.get(talent_id)
            mapping = self.ctx.model_mapping.get(talent_id, {})
            assistant = mapping.get("assistant", "")
            display_name = talent.get("name", talent_id) if talent else talent_id

            state.step_number += 1
            yield EngineEvent(
                "step_start",
                {"talent_id": talent_id, "display_name": display_name, "action": action},
            )

            system_prompt = build_system_prompt(talent or {}, self.ctx.org, self.ctx.org_id, talent_id)
            user_message = build_user_message(
                user_text,
                action=action,
                attachment_context=state.attachment_context,
                prior_responses=prior or None,
            )
            history = state.histories.for_talent(talent_id)
            chunk_buffer: list[str] = []

            def on_chunk(text: str) -> None:
                chunk_buffer.append(text)

            try:
                if assistant == "mock":
                    result = invoke_mock_step(
                        talent_id,
                        state.step_number,
                        stream=state.stream,
                        history=history,
                        user_message=user_message,
                        on_chunk=on_chunk if state.stream else None,
                    )
                    if state.stream:
                        for chunk in chunk_buffer:
                            yield EngineEvent("chunk", {"talent_id": talent_id, "text": chunk})
                elif assistant == "human":
                    briefing = system_prompt
                    response = yield EngineEvent(
                        "await_text",
                        {
                            "talent_id": talent_id,
                            "display_name": display_name,
                            "action": action,
                            "briefing": briefing,
                        },
                    )
                    while not (response and str(response).strip()):
                        response = yield EngineEvent(
                            "await_text",
                            {
                                "talent_id": talent_id,
                                "display_name": display_name,
                                "action": action,
                                "briefing": briefing,
                                "reprompt": True,
                            },
                        )
                    text = str(response).strip()
                    history.add_message(HumanMessage(content=user_message))
                    history.add_message(AIMessage(content=text))
                    result = InvokeResultShim(text)
                else:
                    model = mapping.get("model", "")
                    assistant_cfg = self.ctx.assistants[assistant]
                    result = invoke_llm_step(
                        assistant_name=assistant,
                        assistant_cfg=assistant_cfg,
                        model=model,
                        system_prompt=system_prompt,
                        user_message=user_message,
                        history=history,
                        temperature=state.temperature,
                        stream=state.stream,
                        costs=state.logger.costs,
                        on_chunk=on_chunk if state.stream else None,
                    )
                    if state.stream:
                        for chunk in chunk_buffer:
                            yield EngineEvent("chunk", {"talent_id": talent_id, "text": chunk})
            except Exception as exc:
                yield EngineEvent(
                    "step_error",
                    {"talent_id": talent_id, "error": str(exc), "retry": False},
                )
                continue

            metrics = StepMetrics(
                talent_id=talent_id,
                assistant=assistant,
                model=mapping.get("model"),
                action=action,
                text=result.text,
                stream=getattr(result, "stream", False) if assistant != "human" else False,
                elapsed=result.elapsed,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                tokens_source=result.tokens_source,
                cost=result.cost,
            )
            state.logger.log_step(metrics)
            yield EngineEvent(
                "step_done",
                {
                    "talent_id": talent_id,
                    "assistant": assistant,
                    "model": mapping.get("model"),
                    "text": result.text,
                    "elapsed": result.elapsed,
                    "tokens": {
                        "in": result.tokens_in,
                        "out": result.tokens_out,
                        "source": result.tokens_source,
                    },
                    "cost": result.cost,
                    "stream": metrics.stream,
                },
            )
            prior.append((talent_id, result.text))

        state.logger.log_state_snapshot(
            {"step_number": state.step_number, "talent_ids": resolve_direct_talents(self.ctx)}
        )

    def finish(self) -> EngineEvent:
        if self.state is None:
            raise RuntimeError("session not started")
        self.state.logger.total_elapsed = time.perf_counter() - self.state.session_wall_start
        end_record = self.state.logger.finish()
        return EngineEvent("session_done", end_record)


@dataclass
class InvokeResultShim:
    text: str
    elapsed: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_source: str = "none"
    cost: float = 0.0
    stream: bool = False


def collect_events(
    engine: SessionEngine,
    user_text: str,
    *,
    attachment_context: str = "",
    stream: bool | None = None,
    responder: Callable[[EngineEvent], str | None] | None = None,
) -> list[EngineEvent]:
    events: list[EngineEvent] = []
    gen = engine.run_turn(user_text, attachment_context=attachment_context, stream=stream)
    event = next(gen)
    while True:
        events.append(event)
        if event.type in ("await_text", "await_choice"):
            reply = responder(event) if responder else ""
            try:
                event = gen.send(reply)
            except StopIteration:
                break
            continue
        try:
            event = next(gen)
        except StopIteration:
            break
    events.append(engine.finish())
    return events
