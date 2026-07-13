"""Gradio HTML テンプレート差し替え（lang=ja / 翻訳バー抑制）。"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from jinja2 import ChoiceLoader, FileSystemLoader


def use_japanese_html_template() -> Path:
    """Prefer project templates/gradio over Gradio defaults (keeps toorjson filter)."""
    import gradio.routes as gradio_routes

    template_root = Path(__file__).resolve().parent.parent / "templates" / "gradio"
    gradio_root = Path(
        importlib.resources.files("gradio").joinpath("templates").as_posix()  # type: ignore[attr-defined]
    )
    env = gradio_routes.templates.env
    env.loader = ChoiceLoader(
        [
            FileSystemLoader(str(template_root)),
            FileSystemLoader(str(gradio_root)),
        ]
    )
    return template_root
