"""Git helpers for minutes commit and artifact apply (design.md §7.3, §7.6)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitResult:
    ok: bool
    message: str
    commit_hash: str | None = None


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def is_git_repo(root: Path) -> bool:
    result = _run_git(root, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _porcelain_paths(root: Path) -> set[str]:
    result = _run_git(root, "status", "--porcelain", "-uall")
    if result.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()
        entry = entry.strip('"')
        paths.add(entry.replace("\\", "/"))
    return paths


def has_uncommitted_changes(root: Path, *, excluding: set[str] | None = None) -> bool:
    pending = _porcelain_paths(root)
    if excluding:
        pending -= {p.replace("\\", "/") for p in excluding}
    return bool(pending)


def commit_paths(
    root: Path,
    paths: list[Path],
    message: str,
) -> GitResult:
    root = root.resolve()
    if not is_git_repo(root):
        return GitResult(False, "Git リポジトリではないためコミットをスキップしました")

    rel_paths: list[str] = []
    for path in paths:
        resolved = path.resolve()
        try:
            rel_paths.append(resolved.relative_to(root).as_posix())
        except ValueError:
            return GitResult(False, f"リポジトリ外のパスです: {path}")

    if has_uncommitted_changes(root, excluding=set(rel_paths)):
        return GitResult(
            False,
            "作業ツリーに未コミットの変更があります。議事録保存の前にコミットまたは退避してください。",
        )

    for rel in rel_paths:
        add = _run_git(root, "add", "--", rel)
        if add.returncode != 0:
            return GitResult(False, add.stderr.strip() or add.stdout.strip() or "git add に失敗しました")

    commit = _run_git(root, "commit", "-m", message)
    if commit.returncode != 0:
        detail = commit.stderr.strip() or commit.stdout.strip()
        if "nothing to commit" in detail.lower():
            return GitResult(True, "変更がないためコミットはスキップしました")
        return GitResult(False, detail or "git commit に失敗しました")

    show = _run_git(root, "rev-parse", "--short", "HEAD")
    commit_hash = show.stdout.strip() if show.returncode == 0 else None
    return GitResult(True, f"Git コミットを作成しました（{commit_hash or 'HEAD'}）", commit_hash)
