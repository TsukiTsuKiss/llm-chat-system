"""Artifact extraction from session steps (design.md 7.5) and apply (7.6)."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio.logging import StepMetrics, steps_from_jsonl
from studio.session_report import read_jsonl, session_log_path
from studio.vcs import GitResult, checkout_new_branch, commit_paths, has_uncommitted_changes, is_git_repo

SANDBOX_SKIP_FILES = frozenset({"run_all.sh"})

CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
FILENAME_LINE_RE = re.compile(r"^ファイル名:\s*(\S+)\s*$")
BACKTICK_FILE_RE = re.compile(r"^`?([\w./-]+\.(?:py|js|sh|html|css|json|md))`?\s*$")
COMMENT_FILE_RE = re.compile(r"^#\s*([\w./-]+\.(?:py|js|sh|html|css|json|md))\s*$")

LANG_EXT = {
    "python": "py",
    "py": "py",
    "javascript": "js",
    "js": "js",
    "bash": "sh",
    "sh": "sh",
}


def _safe_relative_path(raw: str) -> str | None:
    path = Path(raw.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _hint_from_prefix(prefix: str) -> str | None:
    lines = prefix.rstrip().splitlines()
    for line in reversed(lines[-8:]):
        stripped = line.strip()
        if not stripped:
            continue
        m = FILENAME_LINE_RE.match(stripped)
        if m:
            return _safe_relative_path(m.group(1))
        m = BACKTICK_FILE_RE.match(stripped)
        if m:
            return _safe_relative_path(m.group(1))
    return None


def _hint_from_code(code: str) -> str | None:
    for line in code.strip().splitlines()[:3]:
        m = COMMENT_FILE_RE.match(line.strip())
        if m:
            return _safe_relative_path(m.group(1))
    return None


def _fallback_name(talent_id: str, action: str, lang: str, index: int) -> str:
    ext = LANG_EXT.get(lang, "txt")
    action_part = (action[:8] or "block").replace(" ", "_")
    return f"code_{talent_id}_{action_part}_{index:02d}.{ext}"


FROM_IMPORT_RE = re.compile(r"from\s+([\w.]+)\s+import\s+([\w]+)")


def _defines_symbol(content: str, symbol: str) -> bool:
    return re.search(rf"^def\s+{re.escape(symbol)}\s*\(", content, re.MULTILINE) is not None


def _is_test_content(content: str, rel: str) -> bool:
    if rel.startswith("test_") or rel.endswith("_test.py"):
        return True
    if "/test_" in rel.replace("\\", "/") or rel.replace("\\", "/").startswith("tests/"):
        return True
    return "import pytest" in content or re.search(r"^def test_", content, re.MULTILINE) is not None


def _should_extract_step(action: str) -> bool:
    """Skip reviewer/judge steps — their code blocks are illustrative, not deliverables."""
    if not action:
        return True
    if action.startswith("終了条件"):
        return False
    if "レビュー" in action:
        return False
    return True


def _is_incomplete_test_snippet(content: str, rel: str) -> bool:
    if not _is_test_content(content, rel):
        return False
    if "import " not in content and "from " not in content:
        return True
    lines = [line for line in content.strip().splitlines() if line.strip() and not line.strip().startswith("#")]
    return len(lines) <= 3 and rel.startswith("code_")


def _prune_junk_artifacts(files: dict[str, str]) -> dict[str, str]:
    has_proper_tests = any(r.replace("\\", "/").startswith("tests/") for r in files)
    result = dict(files)
    to_remove: list[str] = []
    for rel, content in result.items():
        if not rel.endswith((".py", ".js", ".sh", ".html", ".css", ".json", ".md", ".toml")):
            to_remove.append(rel)
            continue
        if rel.startswith("code_") and _is_incomplete_test_snippet(content, rel):
            to_remove.append(rel)
            continue
        if rel.startswith("code_") and _is_test_content(content, rel) and has_proper_tests:
            to_remove.append(rel)
    for rel in to_remove:
        result.pop(rel)
    return result


def normalize_artifact_paths(files: dict[str, str]) -> dict[str, str]:
    """Infer paths from test imports when LLM omitted filename hints."""
    normalized = {
        k: v for k, v in files.items() if k.endswith((".py", ".js", ".sh", ".html", ".css"))
    }
    to_remove: set[str] = set()

    test_rels = [rel for rel, content in normalized.items() if _is_test_content(content, rel)]

    for test_rel in test_rels:
        content = normalized[test_rel]
        imports = FROM_IMPORT_RE.findall(content)

        for module_dotted, symbol in imports:
            module_rel = f"{module_dotted.replace('.', '/')}.py"
            if module_rel in normalized and _defines_symbol(normalized[module_rel], symbol):
                continue

            provider: str | None = None
            for rel, src in normalized.items():
                if rel in to_remove or rel == test_rel:
                    continue
                if _is_test_content(src, rel):
                    continue
                if _defines_symbol(src, symbol):
                    provider = rel
                    break

            if provider and provider != module_rel:
                normalized[module_rel] = normalized[provider]
                to_remove.add(provider)

        if imports and not test_rel.startswith("tests/"):
            module_short = imports[0][0].split(".")[-1]
            new_test_rel = f"tests/test_{module_short}.py"
            if new_test_rel != test_rel:
                normalized[new_test_rel] = content
                to_remove.add(test_rel)

    for rel in to_remove:
        normalized.pop(rel, None)
    return normalized


def _is_runnable_script(content: str, rel: str) -> bool:
    if _is_test_content(content, rel):
        return False
    if "__main__" in content:
        return True
    return "/" not in rel and "\\" not in rel


def extract_code_artifacts(steps: list[StepMetrics]) -> dict[str, str]:
    """Return relative_path -> content (later steps override earlier)."""
    files: dict[str, str] = {}
    for step in steps:
        if not _should_extract_step(step.action or ""):
            continue
        text = step.text or ""
        block_index = 0
        for match in CODE_BLOCK_RE.finditer(text):
            lang = (match.group(1) or "text").lower()
            code = match.group(2).strip()
            if not code:
                continue
            rel = (
                _hint_from_prefix(text[: match.start()])
                or _hint_from_code(code)
                or _fallback_name(step.talent_id, step.action, lang, block_index)
            )
            block_index += 1
            files[rel] = code
    return files


def _ensure_package_inits(session_dir: Path, files: dict[str, str]) -> None:
    """Nested paths (e.g. src/hello.py) need __init__.py for package imports."""
    package_dirs: set[Path] = set()
    for rel in files:
        if not rel.endswith(".py"):
            continue
        parts = Path(rel).parts
        if len(parts) > 1:
            package_dirs.add(Path(*parts[:-1]))
    for package_dir in sorted(package_dirs):
        init_path = session_dir / package_dir / "__init__.py"
        if not init_path.exists():
            init_path.write_text("", encoding="utf-8")


def extract_artifacts_from_log(log_path: Path) -> dict[str, str]:
    """Extract deliverables from a session JSONL without in-memory engine state."""
    return _prune_junk_artifacts(
        normalize_artifact_paths(extract_code_artifacts(steps_from_jsonl(log_path)))
    )


def save_session_artifacts(
    root: Path,
    session_id: str,
    steps: list[StepMetrics] | None = None,
    *,
    log_path: Path | None = None,
) -> Path | None:
    if steps is None:
        if log_path is None:
            return None
        files = extract_artifacts_from_log(log_path)
    else:
        files = _prune_junk_artifacts(normalize_artifact_paths(extract_code_artifacts(steps)))
    if not files:
        return None
    session_dir = root / "sandbox" / f"session_{session_id}"
    if session_dir.exists():
        import shutil

        shutil.rmtree(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        dest = session_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    _ensure_package_inits(session_dir, files)

    run_script = session_dir / "run_all.sh"
    lines = [
        "#!/bin/bash",
        f"# session_{session_id}",
        "set -e",
        'cd "$(dirname "$0")"',
        "export PYTHONPATH=.",
        "",
    ]
    for rel in sorted(files):
        if not rel.endswith(".py"):
            continue
        content = files[rel]
        if _is_test_content(content, rel):
            lines.append(f'echo "=== pytest {rel} ==="')
            lines.append(f"pytest -q {rel}")
            lines.append("")
        elif _is_runnable_script(content, rel):
            lines.append(f'echo "=== python {rel} ==="')
            lines.append(f"python {rel}")
            lines.append("")
    run_script.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return session_dir


@dataclass(frozen=True)
class ApplyArtifactsResult:
    ok: bool
    message: str
    paths: list[Path] | None = None
    git: GitResult | None = None


def sandbox_session_dir(root: Path, session_id: str) -> Path:
    return root / "sandbox" / f"session_{session_id}"


def list_sandbox_artifact_files(session_dir: Path) -> list[Path]:
    if not session_dir.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(session_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(session_dir).as_posix()
        if rel in SANDBOX_SKIP_FILES:
            continue
        if _safe_relative_path(rel) is None:
            continue
        files.append(path)
    return files


def _first_user_input(records: list[dict[str, Any]]) -> str:
    for record in records:
        if record.get("type") == "user_input":
            return str(record.get("text") or "").strip()
    return ""


def apply_commit_message(session_id: str, records: list[dict[str, Any]]) -> str:
    topic = _first_user_input(records)
    summary = (topic[:80] or session_id).replace("\n", " ")
    return f"apply: {summary} (session {session_id})"


def _ensure_sandbox_artifacts(root: Path, session_id: str) -> Path | None:
    session_dir = sandbox_session_dir(root, session_id)
    if list_sandbox_artifact_files(session_dir):
        return session_dir
    log_path = session_log_path(root, session_id)
    if not log_path.is_file():
        return None
    return save_session_artifacts(root, session_id, log_path=log_path)


def apply_session_artifacts(
    root: Path,
    session_id: str,
    *,
    commit: bool = True,
    new_branch: str | None = None,
) -> ApplyArtifactsResult:
    session_id = (session_id or "").strip()
    if not session_id:
        return ApplyArtifactsResult(False, "session_id が未指定です")

    log_path = session_log_path(root, session_id)
    if not log_path.is_file():
        return ApplyArtifactsResult(False, f"セッション `{session_id}` が見つかりません")

    root = root.resolve()
    if is_git_repo(root) and has_uncommitted_changes(root):
        return ApplyArtifactsResult(
            False,
            "作業ツリーに未コミットの変更があります。採用の前にコミットまたは退避してください。",
        )

    session_dir = _ensure_sandbox_artifacts(root, session_id)
    if session_dir is None:
        return ApplyArtifactsResult(False, f"セッション `{session_id}` の sandbox を用意できません")

    source_files = list_sandbox_artifact_files(session_dir)
    if not source_files:
        return ApplyArtifactsResult(False, f"セッション `{session_id}` に採用可能な成果物がありません")

    git_result: GitResult | None = None
    if commit and new_branch and is_git_repo(root):
        git_result = checkout_new_branch(root, new_branch)
        if not git_result.ok:
            return ApplyArtifactsResult(False, git_result.message, git=git_result)

    dest_paths: list[Path] = []
    rel_paths: list[str] = []
    for src in source_files:
        rel = src.relative_to(session_dir).as_posix()
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest_paths.append(dest)
        rel_paths.append(rel)

    message = f"{len(rel_paths)} 件を作業ツリーへ適用しました（`{', '.join(rel_paths[:5])}`"
    if len(rel_paths) > 5:
        message += f" … +{len(rel_paths) - 5}"
    message += "）"

    if commit and is_git_repo(root):
        records = read_jsonl(log_path)
        commit_msg = apply_commit_message(session_id, records)
        git_result = commit_paths(root, dest_paths, commit_msg)
    elif commit and not is_git_repo(root):
        git_result = GitResult(False, "Git リポジトリではないためコミットをスキップしました")

    return ApplyArtifactsResult(True, message, paths=dest_paths, git=git_result)
