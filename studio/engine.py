"""Workflow execution engine (Phase 2: direct send + serial / parallel)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from langchain_core.messages import AIMessage, HumanMessage

from studio.assistants import invoke_llm_step, invoke_mock_step
from studio.bindings import build_direct_bindings, build_direct_workflow, expand_step_to_talents
from studio.history import RoleHistories
from studio.loader import SessionContext
from studio.logging import SessionLogger, StepMetrics
from studio.prompts import build_system_prompt, build_user_message
from studio.validation import StudioError, StudioValidationError


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


@dataclass
class InvokeResultShim:
    text: str
    elapsed: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_source: str = "none"
    cost: float = 0.0
    stream: bool = False


@dataclass
class StepOutcome:
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
        generation = self.ctx.studio_config
        use_stream = generation.get("stream", True) if stream is None else stream
        use_temperature = generation.get("temperature", 0.7) if temperature is None else temperature

        if self.state is None:
            talent_ids = list(self.ctx.org.get("talent_ids") or [])
            logger = SessionLogger.create(
                self.ctx.root,
                self.ctx.org_id,
                workflow=self.ctx.workflow_id,
                talents={
                    tid: self.ctx.talents[tid]
                    for tid in talent_ids
                    if tid in self.ctx.talents
                },
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
                    "workflow": self.ctx.workflow_id,
                    "talents": state.logger.talents,
                },
            )
            state.started = True

        state.logger.log_user_input(user_text)

        workflow, bindings = self._resolve_workflow()
        turn_prior: list[tuple[str, str]] = []

        for phase in workflow.get("phases") or []:
            phase_type = phase.get("type")
            yield EngineEvent("phase_start", {"phase_type": phase_type, "iteration": None})

            if phase_type == "serial":
                yield from self._run_serial_phase(
                    state, user_text, phase, bindings, turn_prior
                )
            elif phase_type == "parallel":
                yield from self._run_parallel_phase(
                    state, user_text, phase, bindings, turn_prior
                )
            elif phase_type == "loop":
                raise StudioValidationError(
                    [
                        StudioError(
                            code="E402",
                            target="workflow",
                            message="loop フェーズは Phase 3 で実装予定です",
                        )
                    ]
                )
            else:
                yield EngineEvent(
                    "step_error",
                    {
                        "talent_id": "",
                        "error": f"未対応のフェーズ種別: {phase_type}",
                        "retry": False,
                    },
                )

        state.logger.log_state_snapshot(
            {
                "step_number": state.step_number,
                "workflow": self.ctx.workflow_id,
                "talent_ids": list(self.ctx.org.get("talent_ids") or []),
            }
        )

    def _resolve_workflow(self) -> tuple[dict[str, Any], dict[str, list[str]]]:
        if self.ctx.workflow_id and self.ctx.workflow and self.ctx.slot_bindings:
            return self.ctx.workflow, self.ctx.slot_bindings
        talent_ids = list(self.ctx.org.get("talent_ids") or [])
        return build_direct_workflow(talent_ids), build_direct_bindings(talent_ids)

    def _run_serial_phase(
        self,
        state: EngineState,
        user_text: str,
        phase: dict[str, Any],
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
    ) -> Iterator[EngineEvent]:
        serial_prior: list[tuple[str, str]] = []
        for step in phase.get("steps") or []:
            for talent_id, action in expand_step_to_talents(step, bindings):
                prior = turn_prior + serial_prior
                gen = self._execute_step(
                    state,
                    user_text,
                    talent_id,
                    action,
                    prior_responses=prior or None,
                    stream=state.stream,
                )
                outcome = yield from gen
                if outcome:
                    serial_prior.append((outcome.talent_id, outcome.text))
        turn_prior.extend(serial_prior)

    def _run_parallel_phase(
        self,
        state: EngineState,
        user_text: str,
        phase: dict[str, Any],
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
    ) -> Iterator[EngineEvent]:
        tasks: list[tuple[str, str, int]] = []
        for step in phase.get("steps") or []:
            for talent_id, action in expand_step_to_talents(step, bindings):
                state.step_number += 1
                tasks.append((talent_id, action, state.step_number))

        if not tasks:
            return

        for talent_id, _, _ in tasks:
            assistant = self.ctx.model_mapping.get(talent_id, {}).get("assistant")
            if assistant == "human":
                raise StudioValidationError(
                    [
                        StudioError(
                            code="E402",
                            target="workflow",
                            message="parallel フェーズに human ロールは Phase 2 未対応です",
                        )
                    ]
                )

        max_workers = min(len(tasks), int(state.ctx.studio_config.get("max_parallel_calls", 8)))
        order = {tid: i for i, (tid, _, _) in enumerate(tasks)}
        outcomes: list[StepOutcome] = []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    self._run_step_sync,
                    state,
                    user_text,
                    talent_id,
                    action,
                    step_no,
                ): talent_id
                for talent_id, action, step_no in tasks
            }
            for future in as_completed(futures):
                outcomes.append(future.result())

        outcomes.sort(key=lambda o: order.get(o.talent_id, 999))

        for outcome in outcomes:
            turn_prior.append((outcome.talent_id, outcome.text))
            display_name = self.ctx.talents.get(outcome.talent_id, {}).get(
                "name", outcome.talent_id
            )
            yield EngineEvent(
                "step_start",
                {
                    "talent_id": outcome.talent_id,
                    "display_name": display_name,
                    "action": outcome.action,
                },
            )
            yield EngineEvent(
                "step_done",
                {
                    "talent_id": outcome.talent_id,
                    "assistant": outcome.assistant,
                    "model": outcome.model,
                    "text": outcome.text,
                    "elapsed": outcome.elapsed,
                    "tokens": {
                        "in": outcome.tokens_in,
                        "out": outcome.tokens_out,
                        "source": outcome.tokens_source,
                    },
                    "cost": outcome.cost,
                    "stream": outcome.stream,
                },
            )

    def _run_step_sync(
        self,
        state: EngineState,
        user_text: str,
        talent_id: str,
        action: str,
        step_number: int,
    ) -> StepOutcome:
        talent = self.ctx.talents.get(talent_id, {})
        mapping = self.ctx.model_mapping.get(talent_id, {})
        assistant = mapping.get("assistant", "")
        system_prompt = build_system_prompt(talent, self.ctx.org, self.ctx.org_id, talent_id)
        user_message = build_user_message(
            user_text,
            action=action,
            attachment_context=state.attachment_context,
        )
        history = state.histories.for_talent(talent_id)

        if assistant == "mock":
            result = invoke_mock_step(
                talent_id,
                step_number,
                stream=False,
                history=history,
                user_message=user_message,
            )
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
                stream=False,
                costs=state.logger.costs,
            )

        metrics = StepMetrics(
            talent_id=talent_id,
            assistant=assistant,
            model=mapping.get("model"),
            action=action,
            text=result.text,
            stream=False,
            elapsed=result.elapsed,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_source=result.tokens_source,
            cost=result.cost,
        )
        state.logger.log_step(metrics)
        return StepOutcome(
            talent_id=talent_id,
            assistant=assistant,
            model=mapping.get("model"),
            action=action,
            text=result.text,
            stream=False,
            elapsed=result.elapsed,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_source=result.tokens_source,
            cost=result.cost,
        )

    def _execute_step(
        self,
        state: EngineState,
        user_text: str,
        talent_id: str,
        action: str,
        *,
        prior_responses: list[tuple[str, str]] | None,
        stream: bool,
    ) -> Iterator[EngineEvent, None, StepOutcome | None]:
        talent = self.ctx.talents.get(talent_id, {})
        mapping = self.ctx.model_mapping.get(talent_id, {})
        assistant = mapping.get("assistant", "")
        display_name = talent.get("name", talent_id)

        state.step_number += 1
        yield EngineEvent(
            "step_start",
            {"talent_id": talent_id, "display_name": display_name, "action": action},
        )

        system_prompt = build_system_prompt(
            talent, self.ctx.org, self.ctx.org_id, talent_id
        )
        user_message = build_user_message(
            user_text,
            action=action,
            attachment_context=state.attachment_context,
            prior_responses=prior_responses,
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
                    stream=stream,
                    history=history,
                    user_message=user_message,
                    on_chunk=on_chunk if stream else None,
                )
                if stream:
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
                result = InvokeResultShim(text, stream=False)
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
                    stream=stream,
                    costs=state.logger.costs,
                    on_chunk=on_chunk if stream else None,
                )
                if stream:
                    for chunk in chunk_buffer:
                        yield EngineEvent("chunk", {"talent_id": talent_id, "text": chunk})
        except Exception as exc:
            yield EngineEvent(
                "step_error",
                {"talent_id": talent_id, "error": str(exc), "retry": False},
            )
            return None

        step_stream = getattr(result, "stream", False) if assistant != "human" else False
        metrics = StepMetrics(
            talent_id=talent_id,
            assistant=assistant,
            model=mapping.get("model"),
            action=action,
            text=result.text,
            stream=step_stream,
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
                "stream": step_stream,
            },
        )
        return StepOutcome(
            talent_id=talent_id,
            assistant=assistant,
            model=mapping.get("model"),
            action=action,
            text=result.text,
            stream=step_stream,
            elapsed=result.elapsed,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_source=result.tokens_source,
            cost=result.cost,
        )

    def finish(self) -> EngineEvent:
        if self.state is None:
            raise RuntimeError("session not started")
        self.state.logger.total_elapsed = time.perf_counter() - self.state.session_wall_start
        end_record = self.state.logger.finish()
        return EngineEvent("session_done", end_record)


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
