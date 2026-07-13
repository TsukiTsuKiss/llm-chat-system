#!/usr/bin/env python3
"""MultiRoleStudio CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from studio.assistants import MockAssistant
from studio.bindings import org_has_human_talent, workflow_participating_talent_ids
from studio.display import format_session_end_lines, format_step_metrics_line
from studio.engine import EngineEvent, SessionEngine, collect_events
from studio.loader import load_session_context, read_attachment_files
from studio.validation import StudioError, StudioValidationError
from studio.workflow_validate import workflow_has_user_exit

VERSION = "0.3.0"


def print_event(event: EngineEvent, *, use_stream: bool) -> None:
    if event.type == "session_start":
        p = event.payload
        wf = p.get("workflow") or "直接送信"
        print(f"\n=== MultiRoleStudio session {p['session_id']} ===")
        print(f"組織: {p['org']} / {wf}")
    elif event.type == "phase_start" and not event.payload.get("phase_end"):
        phase_type = event.payload.get("phase_type", "serial")
        iteration = event.payload.get("iteration")
        suffix = f" (反復 {iteration})" if iteration else ""
        print(f"\n--- phase: {phase_type}{suffix} ---")
    elif event.type == "loop_check":
        p = event.payload
        print(
            f"\n[loop] 反復 {p['iteration']}: {p['exit_type']} → {p['result']}"
        )
    elif event.type == "await_choice":
        p = event.payload
        print(f"\n{p.get('prompt', '続けますか？')} (y=続行 / n=終了)")
    elif event.type == "step_start":
        p = event.payload
        print(f"\n--- {p['display_name']} ---")
    elif event.type == "chunk":
        if use_stream:
            print(event.payload["text"], end="", flush=True)
    elif event.type == "step_done":
        p = event.payload
        if use_stream:
            print()
        else:
            print(p["text"])
        print(format_step_metrics_line(p))
    elif event.type == "step_error":
        print(f"❌ {event.payload['talent_id']}: {event.payload['error']}")
    elif event.type == "await_text":
        p = event.payload
        print(f"\n[{p['display_name']} として発言]")
        if p.get("briefing"):
            print(p["briefing"])
    elif event.type == "session_done":
        for line in format_session_end_lines(event.payload):
            print(line)


def drive_interactive_responder(event: EngineEvent) -> str | None:
    if event.type == "await_text":
        return input("> ")
    if event.type == "await_choice":
        raw = input("> ").strip().lower()
        return "exit" if raw in {"n", "no", "exit", "終了"} else "continue"
    return None


def validate_batch_mode(ctx, topic: str | None) -> None:
    if not topic:
        return
    participant_ids = workflow_participating_talent_ids(ctx.org, ctx.slot_bindings)
    if org_has_human_talent(ctx.model_mapping, participant_ids):
        wf_label = ctx.workflow_id or "直接送信"
        raise StudioValidationError(
            [
                StudioError(
                    code="E402",
                    target="--topic",
                    message=(
                        f"ワークフロー '{wf_label}' は human 参加を含むため"
                        " --topic による無人実行はできません"
                    ),
                )
            ]
        )

    if ctx.workflow and workflow_has_user_exit(ctx.workflow):
        wf_label = ctx.workflow_id or "ワークフロー"
        raise StudioValidationError(
            [
                StudioError(
                    code="E402",
                    target="--topic",
                    message=(
                        f"ワークフロー '{wf_label}' は exit.type \"user\" を含むため"
                        " --topic による無人実行はできません"
                    ),
                )
            ]
        )


def run_batch(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        ctx = load_session_context(args.org, root, workflow_id=args.workflow)
        validate_batch_mode(ctx, args.topic)
    except StudioValidationError as exc:
        print(exc.format_all(), file=sys.stderr)
        return 1

    attachment_context = ""
    if args.files:
        limits = ctx.studio_config.get("upload_limits", {})
        attachment_context, report = read_attachment_files([Path(p) for p in args.files], limits)
        if not report.ok:
            print(report.errors[0].format(), file=sys.stderr)
            return 1

    MockAssistant.reset()
    engine = SessionEngine(ctx)
    use_stream = ctx.studio_config.get("stream", True) if args.stream is None else args.stream

    events = collect_events(
        engine,
        args.topic,
        attachment_context=attachment_context,
        stream=use_stream,
    )
    for event in events:
        print_event(event, use_stream=use_stream)
    return 0


def run_interactive(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        ctx = load_session_context(args.org, root, workflow_id=args.workflow)
    except StudioValidationError as exc:
        print(exc.format_all(), file=sys.stderr)
        return 1

    MockAssistant.reset()
    engine = SessionEngine(ctx)
    use_stream = ctx.studio_config.get("stream", True) if args.stream is None else args.stream

    print("MultiRoleStudio 対話モード（終了: q）")
    while True:
        try:
            user_text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text or user_text.lower() in {"q", "quit", "exit"}:
            break

        gen = engine.run_turn(user_text, stream=use_stream)
        event = next(gen)
        while True:
            print_event(event, use_stream=use_stream)
            if event.type in ("await_text", "await_choice"):
                reply = drive_interactive_responder(event)
                try:
                    event = gen.send(reply)
                except StopIteration:
                    break
                continue
            try:
                event = next(gen)
            except StopIteration:
                break

    if engine.state and engine.state.started:
        print_event(engine.finish(), use_stream=use_stream)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MultiRoleStudio CLI")
    parser.add_argument("--org", default="solo", help="組織 ID")
    parser.add_argument("--workflow", default=None, help="ワークフロー ID（discussion / quiz 等）")
    parser.add_argument("--topic", default=None, help="バッチ実行の議題（指定時は無人完走）")
    parser.add_argument("--files", nargs="*", default=None, help="添付ファイル")
    parser.add_argument("--root", default=".", help="プロジェクトルート")
    parser.add_argument(
        "--stream",
        choices=("on", "off"),
        default=None,
        help="ストリーミング ON/OFF（未指定時は studio_config）",
    )
    parser.add_argument("--version", action="version", version=f"MultiRoleStudio {VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stream == "on":
        args.stream = True
    elif args.stream == "off":
        args.stream = False

    if args.topic:
        return run_batch(args)
    return run_interactive(args)


if __name__ == "__main__":
    raise SystemExit(main())
