"""Gradio HTML テンプレート差し替え（lang=ja / 翻訳バー抑制）。"""

from __future__ import annotations

import importlib.resources
import tempfile
from pathlib import Path

from jinja2 import ChoiceLoader, FileSystemLoader

_HTML_OPEN = '<html\n\tlang="en"'
_HEAD_OPEN = '<meta charset="utf-8" />'
_JA_HTML_OPEN = '<html\n\tlang="ja"\n\ttranslate="no"\n\tclass="notranslate"'
_JA_HEAD_META = (
    '<meta charset="utf-8" />\n'
    '\t\t<meta name="google" content="notranslate" />\n'
    '\t\t<meta http-equiv="content-language" content="ja" />'
)


def _japanese_index_html(source: str) -> str:
    """インストール済み Gradio の index.html に lang=ja / notranslate だけを足す。

    asset のハッシュは Gradio のバージョンごとに変わるため、固定コピーは持たず毎回生成する。
    """
    html = source.replace(_HTML_OPEN, _JA_HTML_OPEN, 1).replace(_HEAD_OPEN, _JA_HEAD_META, 1)
    if 'lang="ja"' not in html:
        raise RuntimeError("Gradio の index.html の形式が想定と異なり、日本語テンプレートを作れません")
    return html


def use_japanese_html_template() -> Path:
    """Gradio の HTML テンプレートを lang=ja 版に差し替える（toorjson フィルタは Gradio のものを使う）。"""
    import gradio.routes as gradio_routes

    gradio_root = Path(
        importlib.resources.files("gradio").joinpath("templates").as_posix()  # type: ignore[attr-defined]
    )
    source = (gradio_root / "frontend" / "index.html").read_text(encoding="utf-8")

    template_root = Path(tempfile.mkdtemp(prefix="multirolestudio_gradio_"))
    (template_root / "frontend").mkdir()
    (template_root / "frontend" / "index.html").write_text(_japanese_index_html(source), encoding="utf-8")

    env = gradio_routes.templates.env
    env.loader = ChoiceLoader(
        [
            FileSystemLoader(str(template_root)),
            FileSystemLoader(str(gradio_root)),
        ]
    )
    return template_root
