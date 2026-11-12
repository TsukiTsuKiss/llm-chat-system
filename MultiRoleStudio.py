#!/usr/bin/env python3
"""MultiRoleStudio CLI."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from studio.artifacts import apply_session_artifacts
from studio.assistants import MockAssistant
from studio.benchmark import format_summary_table, load_questions, miss_lines, run_benchmark
from studio.bindings import org_has_human_talent, workflow_participating_talent_ids
from studio.display import format_session_end_lines, format_step_metrics_line
from studio.engine import EngineEvent, SessionEngine, collect_events
from studio.loader import load_session_context, load_studio_config, read_attachment_files
from studio.user_context_rag import reindex_corpus
from studio.user_context_update import (
    apply_context_draft,
    save_context_draft_from_session,
    save_summary_from_context,
)
from studio.validation import StudioError, StudioValidationError
from studio.voice import (
    DEFAULT_BASE_URL,
    VoiceReader,
    engine_available,
    load_voice_dictionary,
    load_voice_mapping,
    parse_voicevox_urls,
)
from studio.workflow_validate import workflow_has_interrupt_on, workflow_has_user_exit

VERSION = "0.7.7"


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
        if p.get("interrupt"):
            speaker = p.get("prior_speaker", "AI")
            print(f"\n[{speaker} からの質問]")
            if p.get("prior_text"):
                print(f"--- {p['prior_text']}")
            print("[あなたの回答]")
        else:
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

    if ctx.workflow and workflow_has_interrupt_on(ctx.workflow):
        wf_label = ctx.workflow_id or "ワークフロー"
        raise StudioValidationError(
            [
                StudioError(
                    code="E402",
                    target="--topic",
                    message=(
                        f"ワークフロー '{wf_label}' は interrupt_on を含むため"
                        " --topic による無人実行はできません"
                    ),
                )
            ]
        )


def voice_requested(args: argparse.Namespace) -> bool:
    # --voicevox-url を明示したときは、--voice がなくても読み上げる
    return bool(args.voice) or args.voicevox_url is not None


def create_voice_reader(args: argparse.Namespace, ctx) -> VoiceReader | None:
    if not voice_requested(args):
        return None
    voicevox_url = args.voicevox_url or DEFAULT_BASE_URL
    mapping = load_voice_mapping(ctx.root, ctx.org_id)
    if not mapping:
        print(f"[voice] organizations/{ctx.org_id}/voice_mapping.json がないため読み上げません", file=sys.stderr)
        return None
    configured = parse_voicevox_urls(voicevox_url)
    urls = [url for url in configured if engine_available(url)]
    if not urls:
        print(f"[voice] VOICEVOX ({voicevox_url}) に接続できないため読み上げません", file=sys.stderr)
        return None
    for url in configured:
        if url not in urls:
            print(f"[voice] 接続できない VOICEVOX を外しました: {url}", file=sys.stderr)
    return VoiceReader(
        ctx.root,
        mapping,
        base_url=urls,
        dictionary=load_voice_dictionary(ctx.root, ctx.org_id),
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
        no_user_context=args.no_user_context,
        no_user_context_rag=args.no_user_context_rag,
        web_search=args.web_search,
    )
    voice = create_voice_reader(args, ctx)
    for event in events:
        print_event(event, use_stream=use_stream)
        if voice:
            voice.handle(event)
    if voice:
        voice.close()
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
    voice = create_voice_reader(args, ctx)

    print("MultiRoleStudio 対話モード（終了: q）")
    while True:
        try:
            user_text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text or user_text.lower() in {"q", "quit", "exit"}:
            break

        gen = engine.run_turn(
            user_text,
            stream=use_stream,
            no_user_context=args.no_user_context,
            no_user_context_rag=args.no_user_context_rag,
            web_search=args.web_search,
        )
        event = next(gen)
        while True:
            print_event(event, use_stream=use_stream)
            if voice:
                voice.handle(event)
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
        end_event = engine.finish()
        print_event(end_event, use_stream=use_stream)
    if voice:
        voice.close()
    return 0


def run_benchmark_cli(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        ctx = load_session_context(args.org, root)
        questions = load_questions(Path(args.benchmark))
        talent_ids = [t.strip() for t in args.talents.split(",") if t.strip()] if args.talents else None
        max_parallel = args.max_parallel or int(ctx.studio_config.get("max_parallel_calls", 8))
        report = run_benchmark(
            ctx,
            questions,
            out_root=root / args.bench_out,
            trials=args.trials,
            style=args.style,
            talent_ids=talent_ids,
            max_parallel=max_parallel,
            per_provider=args.per_provider,
            rpm=args.rpm,
            retries=args.retries,
            temperature=args.temperature,
            progress=print,
            questions_path=Path(args.benchmark),
            command="python MultiRoleStudio.py " + shlex.join(args.argv),
        )
    except StudioValidationError as exc:
        print(exc.format_all(), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"[benchmark] {exc}", file=sys.stderr)
        return 1
    print("\n" + format_summary_table(report.summary))
    for line in miss_lines(report.rows):
        print(line)
    print(f"\n結果: {report.out_dir}")
    return 0


def run_apply(args: argparse.Namespace) -> int:
    root = Path(args.root)
    branch = f"studio/{args.apply}" if args.apply_branch else None
    result = apply_session_artifacts(
        root,
        args.apply,
        commit=True,
        new_branch=branch,
    )
    print(result.message)
    if result.git and not result.git.ok and result.ok:
        print(result.git.message, file=sys.stderr)
    return 0 if result.ok else 1


def run_user_context_draft(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result = save_context_draft_from_session(root, args.user_context_draft)
    print(result.message)
    return 0 if result.ok else 1


def run_user_context_apply(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result = apply_context_draft(root, args.user_context_apply)
    print(result.message)
    return 0 if result.ok else 1


def run_user_context_summarize(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result = save_summary_from_context(root)
    print(result.message)
    return 0 if result.ok else 1


def run_user_context_reindex(args: argparse.Namespace) -> int:
    root = Path(args.root)
    try:
        studio_config = load_studio_config(root)
    except StudioValidationError as exc:
        print(exc.format_all(), file=sys.stderr)
        return 1
    result = reindex_corpus(root, studio_config)
    print(result.message)
    return 0 if result.ok else 1


def _temperature_arg(value: str) -> float | None:
    if value.lower() == "default":
        return None
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"数値か default を指定してください: {value}") from None


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
    parser.add_argument(
        "--web-search",
        action="store_true",
        help="ウェブ検索を有効にする（model_mapping で web_search: true の人材のみ）",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="VOICEVOX で発言を読み上げ、sessions/audio/<session_id>/ に wav を保存する（--voicevox-url を指定したときも有効）",
    )
    parser.add_argument(
        "--voicevox-url",
        default=None,
        help=f"VOICEVOX の接続先。指定すると読み上げを有効にする（このオプションなしで --voice のみのときの既定: {DEFAULT_BASE_URL}）。カンマ区切りで複数指定すると並列合成",
    )
    parser.add_argument(
        "--apply",
        metavar="SESSION_ID",
        default=None,
        help="sandbox 成果物を作業ツリーへ適用し Git コミット（7.6 節）",
    )
    parser.add_argument(
        "--apply-branch",
        action="store_true",
        help="--apply 時に studio/<session_id> ブランチを作成してからコミット",
    )
    parser.add_argument(
        "--no-user-context",
        action="store_true",
        help="ユーザーコンテキスト（付録D）を今回のセッションでは注入しない",
    )
    parser.add_argument(
        "--no-user-context-rag",
        action="store_true",
        help="user_context RAG（付録D.10）のみ今回のセッションでは注入しない",
    )
    parser.add_argument(
        "--user-context-draft",
        metavar="SESSION_ID",
        default=None,
        help="セッションから user_context 更新案を生成（付録D.7）",
    )
    parser.add_argument(
        "--user-context-apply",
        metavar="SESSION_ID",
        default=None,
        help="更新案を my_context.md の蓄積メモへ追記（付録D.7）",
    )
    parser.add_argument(
        "--user-context-summarize",
        action="store_true",
        help="my_context.md から要約版 my_context.summary.md を生成（付録D.8）",
    )
    parser.add_argument(
        "--user-context-reindex",
        action="store_true",
        help="user_context/corpus を index 再構築（付録D.10）",
    )
    parser.add_argument(
        "--benchmark",
        metavar="QUESTIONS",
        default=None,
        help="問題セット（JSON / JSONL）を組織の全モデルに流し、自動採点して集計する",
    )
    parser.add_argument("--trials", type=int, default=1, help="--benchmark: 同じ問題を何回ずつ流すか（既定: 1）")
    parser.add_argument(
        "--style",
        choices=("answer", "reason"),
        default="reason",
        help="--benchmark: answer=答えだけ / reason=簡潔な理由つき（既定）",
    )
    parser.add_argument("--talents", default=None, help="--benchmark: 対象の人材 ID（カンマ区切り。既定は組織の全員）")
    parser.add_argument("--max-parallel", type=int, default=None, help="--benchmark: 全体の同時実行数（既定: studio_config の max_parallel_calls）")
    parser.add_argument("--per-provider", type=int, default=4, help="--benchmark: プロバイダーごとの同時実行数（既定: 4）")
    parser.add_argument("--rpm", type=float, default=None, help="--benchmark: モデルごとの 1 分あたりの呼び出し上限（レート制限の回避。既定: 制限なし）")
    parser.add_argument("--retries", type=int, default=2, help="--benchmark: 失敗した呼び出しの再試行回数（既定: 2）")
    parser.add_argument(
        "--temperature",
        type=_temperature_arg,
        default=0.0,
        help="--benchmark: temperature（既定: 0。default でプロバイダー既定値）",
    )
    parser.add_argument("--bench-out", default="benchmark_results", help="--benchmark: 結果の出力先（既定: benchmark_results）")
    parser.add_argument("--version", action="version", version=f"MultiRoleStudio {VERSION}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.argv = list(sys.argv[1:] if argv is None else argv)
    if args.stream == "on":
        args.stream = True
    elif args.stream == "off":
        args.stream = False

    if args.user_context_draft:
        return run_user_context_draft(args)
    if args.user_context_apply:
        return run_user_context_apply(args)
    if args.user_context_summarize:
        return run_user_context_summarize(args)
    if args.user_context_reindex:
        return run_user_context_reindex(args)

    if args.apply:
        return run_apply(args)

    if args.benchmark:
        return run_benchmark_cli(args)

    if args.topic:
        return run_batch(args)
    return run_interactive(args)


if __name__ == "__main__":
    raise SystemExit(main())
