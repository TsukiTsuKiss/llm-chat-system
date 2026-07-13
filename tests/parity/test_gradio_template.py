"""Gradio Japanese HTML template hook tests."""

from pathlib import Path

from studio.gradio_template import use_japanese_html_template


def test_japanese_template_has_lang_ja() -> None:
    root = use_japanese_html_template()
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'lang="ja"' in html
    assert 'lang="en"' not in html.split("<head>", 1)[0]
    assert "notranslate" in html
