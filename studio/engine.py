"""Workflow execution engine (Phase 3: serial / parallel / loop)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from langchain_core.messages import AIMessage, HumanMessage

from studio.assistants import invoke_llm_step, invoke_mock_step
from studio.bindings import build_direct_bindings, build_direct_workflow, expand_step_to_talents
from studio.history import ConversationHistory, RoleHistories
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
    logger: SessionLogger | None = None
    histories: RoleHistories = field(default_factory=RoleHistories)
    step_number: int = 0
    stream: bool = True
    temperature: float | None = 0.7
    attachment_context: str = ""
    started: bool = False
    session_wall_start: float = 0.0
    parent_session_id: str | None = None


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
        attachments: list[str] | None = None,
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
            if state.logger is None:
                if not state.parent_session_id:
                    raise RuntimeError("resume session requires parent_session_id")
                talent_ids = list(self.ctx.org.get("talent_ids") or [])
                state.logger = SessionLogger.create_branch(
                    self.ctx.root,
                    state.parent_session_id,
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
            state.logger.start()
            yield EngineEvent(
                "session_start",
                {
                    "session_id": state.logger.session_id,
                    "org": self.ctx.org_id,
                    "workflow": self.ctx.workflow_id,
                    "talents": state.logger.talents,
                    "parent_session_id": state.parent_session_id,
                    "resumed_from": state.parent_session_id,
                },
            )
            state.started = True

        assert state.logger is not None
        state.logger.log_user_input(user_text, attachments=attachments)

        workflow, bindings = self._resolve_workflow()
        turn_prior: list[tuple[str, str]] = []

        yield from self._run_phases(
            workflow.get("phases") or [],
            state,
            user_text,
            bindings,
            turn_prior,
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

    def _speaker_label(self, talent_id: str) -> str:
        return self.ctx.talents.get(talent_id, {}).get("name", talent_id)

    def _run_phases(
        self,
        phases: list[dict[str, Any]],
        state: EngineState,
        user_text: str,
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
        *,
        loop_phase: dict[str, Any] | None = None,
        iteration: int | None = None,
    ) -> Iterator[EngineEvent]:
        marker_target: tuple[str, str] | None = None
        marker_text: str | None = None
        if loop_phase and (loop_phase.get("exit") or {}).get("type") == "marker":
            marker_text = loop_phase["exit"].get("marker")
            marker_target = self._loop_marker_target(loop_phase, bindings)

        for phase in phases:
            phase_type = phase.get("type")
            if phase_type == "loop":
                yield from self._run_loop_phase(
                    state, user_text, phase, bindings, turn_prior
                )
                continue

            yield EngineEvent(
                "phase_start",
                {"phase_type": phase_type, "iteration": iteration},
            )

            if phase_type == "serial":
                yield from self._run_serial_phase(
                    state,
                    user_text,
                    phase,
                    bindings,
                    turn_prior,
                    marker_target=marker_target,
                    marker_text=marker_text,
                )
            elif phase_type == "parallel":
                yield from self._run_parallel_phase(
                    state, user_text, phase, bindings, turn_prior
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

    def _loop_marker_target(
        self,
        loop_phase: dict[str, Any],
        bindings: dict[str, list[str]],
    ) -> tuple[str, str] | None:
        inner = loop_phase.get("phases") or []
        if not inner or inner[-1].get("type") != "serial":
            return None
        steps = inner[-1].get("steps") or []
        if not steps:
            return None
        expanded = expand_step_to_talents(steps[-1], bindings)
        return expanded[-1] if expanded else None

    def _run_loop_phase(
        self,
        state: EngineState,
        user_text: str,
        phase: dict[str, Any],
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
    ) -> Iterator[EngineEvent]:
        exit_cfg = phase.get("exit") or {}
        exit_type = exit_cfg.get("type")
        max_iter = phase.get("max_iterations", 999999 if exit_type == "user" else 1)
        inner_phases = phase.get("phases") or []

        for iteration in range(1, max_iter + 1):
            iter_start_len = len(turn_prior)
            yield EngineEvent(
                "phase_start",
                {"phase_type": "loop", "iteration": iteration},
            )
            yield from self._run_phases(
                inner_phases,
                state,
                user_text,
                bindings,
                turn_prior,
                loop_phase=phase,
                iteration=iteration,
            )

            last_text = turn_prior[-1][1] if len(turn_prior) > iter_start_len else ""
            should_exit = False
            reason = ""

            if exit_type == "marker":
                marker = exit_cfg.get("marker", "")
                should_exit = bool(marker and marker in last_text)
                reason = f"marker '{marker}' {'detected' if should_exit else 'not found'}"
            elif exit_type == "judge":
                outcome = yield from self._run_judge_step(
                    state,
                    user_text,
                    exit_cfg.get("slot", ""),
                    exit_cfg.get("criteria", ""),
                    bindings,
                    turn_prior,
                )
                should_exit = "【判定】終了" in (outcome.text if outcome else "")
                reason = outcome.text if outcome else ""
            elif exit_type == "user":
                prompt = exit_cfg.get("prompt", "続けますか？")
                choice = yield EngineEvent(
                    "await_choice",
                    {
                        "prompt": prompt,
                        "choices": ["continue", "exit"],
                    },
                )
                should_exit = choice == "exit"
                reason = f"user chose {choice}"
            else:
                should_exit = iteration >= max_iter
                reason = "max_iterations reached"

            yield EngineEvent(
                "loop_check",
                {
                    "iteration": iteration,
                    "exit_type": exit_type or "max_iterations",
                    "result": "exit" if should_exit else "continue",
                    "reason": reason,
                },
            )
            if should_exit:
                break
            if exit_type != "user" and iteration >= max_iter:
                break

    def _run_judge_step(
        self,
        state: EngineState,
        user_text: str,
        slot: str,
        criteria: str,
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
    ) -> Iterator[EngineEvent, None, StepOutcome | None]:
        talent_ids = bindings.get(slot, [])
        if not talent_ids:
            return None
        talent_id = talent_ids[0]
        action = (
            f"終了条件: {criteria}\n\n"
            "出力は必ず「【判定】継続」または「【判定】終了」で始め、理由を続けてください。"
        )
        ephemeral = ConversationHistory()
        talent = self.ctx.talents.get(talent_id, {})
        mapping = self.ctx.model_mapping.get(talent_id, {})
        assistant = mapping.get("assistant", "")
        display_name = talent.get("name", talent_id)

        state.step_number += 1
        yield EngineEvent(
            "step_start",
            {"talent_id": talent_id, "display_name": display_name, "action": action, "judge": True},
        )

        system_prompt = build_system_prompt(
            talent, self.ctx.org, self.ctx.org_id, talent_id
        )
        user_message = build_user_message(
            user_text,
            action=action,
            attachment_context=state.attachment_context,
            prior_responses=turn_prior or None,
        )

        try:
            if assistant == "mock":
                result = invoke_mock_step(
                    talent_id,
                    state.step_number,
                    stream=False,
                    history=ephemeral,
                    user_message=user_message,
                    action=action,
                )
            elif assistant == "human":
                briefing = system_prompt
                response = yield EngineEvent(
                    "await_text",
                    {
                        "talent_id": talent_id,
                        "display_name": display_name,
                        "action": action,
                        "briefing": briefing,
                        "judge": True,
                    },
                )
                text = str(response or "").strip()
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
                    history=ephemeral,
                    temperature=state.temperature,
                    stream=False,
                    costs=state.logger.costs,
                )
        except Exception as exc:
            yield EngineEvent(
                "step_error",
                {"talent_id": talent_id, "error": str(exc), "retry": False},
            )
            return None

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
                "stream": False,
                "judge": True,
            },
        )
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

    def _inject_marker_action(
        self,
        talent_id: str,
        action: str,
        marker_target: tuple[str, str] | None,
        marker_text: str | None,
    ) -> str:
        if not marker_target or not marker_text:
            return action
        if (talent_id, action) != marker_target:
            return action
        return (
            f"{action}\n\n"
            f"（終了条件）合意・結論に至った場合は応答に「{marker_text}」を含めてください。"
        )

    def _run_serial_phase(
        self,
        state: EngineState,
        user_text: str,
        phase: dict[str, Any],
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
        *,
        marker_target: tuple[str, str] | None = None,
        marker_text: str | None = None,
    ) -> Iterator[EngineEvent]:
        serial_prior: list[tuple[str, str]] = []
        for step in phase.get("steps") or []:
            for talent_id, action in expand_step_to_talents(step, bindings):
                action = self._inject_marker_action(talent_id, action, marker_target, marker_text)
                prior = turn_prior + serial_prior
                gen = self._execute_step(
                    state,
                    user_text,
                    talent_id,
                    action,
                    prior_responses=prior or None,
                    stream=state.stream,
                    phase_type="serial",
                )
                outcome = yield from gen
                if outcome:
                    serial_prior.append((self._speaker_label(outcome.talent_id), outcome.text))
        turn_prior.extend(serial_prior)

    def _run_parallel_phase(
        self,
        state: EngineState,
        user_text: str,
        phase: dict[str, Any],
        bindings: dict[str, list[str]],
        turn_prior: list[tuple[str, str]],
    ) -> Iterator[EngineEvent]:
        tasks: list[tuple[str, str]] = []
        for step in phase.get("steps") or []:
            for talent_id, action in expand_step_to_talents(step, bindings):
                tasks.append((talent_id, action))

        if not tasks:
            return

        ai_tasks: list[tuple[str, str]] = []
        human_tasks: list[tuple[str, str]] = []
        for talent_id, action in tasks:
            assistant = self.ctx.model_mapping.get(talent_id, {}).get("assistant")
            if assistant == "human":
                human_tasks.append((talent_id, action))
            else:
                ai_tasks.append((talent_id, action))

        order = {tid: i for i, (tid, _) in enumerate(tasks)}
        outcomes: list[StepOutcome] = []

        if ai_tasks:
            max_workers = min(
                len(ai_tasks), int(state.ctx.studio_config.get("max_parallel_calls", 8))
            )
            ai_step_numbers: list[tuple[str, str, int]] = []
            for talent_id, action in ai_tasks:
                state.step_number += 1
                ai_step_numbers.append((talent_id, action, state.step_number))

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        self._run_step_sync,
                        state,
                        user_text,
                        talent_id,
                        action,
                        step_no,
                        "parallel",
                    ): talent_id
                    for talent_id, action, step_no in ai_step_numbers
                }
                for future in as_completed(futures):
                    outcomes.append(future.result())

            outcomes.sort(key=lambda o: order.get(o.talent_id, 999))

            for outcome in outcomes:
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

        for talent_id, action in human_tasks:
            prior = turn_prior + [
                (self._speaker_label(o.talent_id), o.text) for o in outcomes
            ]
            outcome = yield from self._execute_step(
                state,
                user_text,
                talent_id,
                action,
                prior_responses=prior or None,
                stream=state.stream,
                phase_type="parallel",
            )
            if outcome:
                outcomes.append(outcome)

        outcomes.sort(key=lambda o: order.get(o.talent_id, 999))
        turn_prior.extend((self._speaker_label(o.talent_id), o.text) for o in outcomes)

    def _run_step_sync(
        self,
        state: EngineState,
        user_text: str,
        talent_id: str,
        action: str,
        step_number: int,
        phase_type: str | None = None,
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
                action=action,
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
            phase_type=phase_type,
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
        phase_type: str | None = None,
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
                    action=action,
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
            phase_type=phase_type,
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
        from studio.artifacts import save_session_artifacts

        self.state.logger.total_elapsed = time.perf_counter() - self.state.session_wall_start
        artifact_dir = save_session_artifacts(
            self.state.ctx.root,
            self.state.logger.session_id,
            log_path=self.state.logger.log_path,
        )
        end_record = self.state.logger.finish()
        if artifact_dir:
            end_record["artifact_dir"] = str(artifact_dir)
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
            if event.type == "await_choice" and not reply:
                reply = "continue"
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
