"""デモ用ルートの準備を検証する。"""

import json
import shutil
from pathlib import Path

import pytest

from demo import make_demo
from studio.benchmark import load_questions


@pytest.fixture
def demo_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("schemas", "talents", "workflows", "samples/benchmark", "organizations/broadcast_studio"):
        (repo / name).mkdir(parents=True)
    for name in ("ai_assistants_config.json", "model_costs.csv"):
        (repo / name).write_text("", encoding="utf-8")
    for talent in make_demo.BROADCAST_TALENTS:
        (repo / "talents" / f"{talent}.json").write_text("{}", encoding="utf-8")
    sample = Path(__file__).resolve().parents[2] / "samples/benchmark/questions.example.json"
    shutil.copy2(sample, repo / "samples/benchmark/questions.example.json")
    org = repo / "organizations/broadcast_studio"
    (org / "model_mapping.example.json").write_text('{"midori": {"assistant": "mock"}}', encoding="utf-8")
    (repo / "studio_config.example.json").write_text(
        json.dumps({
            "temperature": 0.7,
            "user_context": {
                "enabled": False,
                "path": "/elsewhere/context.md",
                "rag": {"enabled": False, "corpus_dir": "/elsewhere/corpus", "index_dir": "/elsewhere/index", "top_k": 3},
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(make_demo, "REPO", repo)
    root = tmp_path / "demo_root"
    root.mkdir()
    monkeypatch.setattr(make_demo.tempfile, "mkdtemp", lambda **kwargs: str(root))
    return repo, root


@pytest.mark.parametrize("mock", [True, False])
def test_build_demo_root_uses_bundled_questions_and_settings(demo_repo, mock):
    repo, root = demo_repo
    org = repo / "organizations/broadcast_studio"
    if not mock:
        (org / "model_mapping.json").write_text('{"midori": {"assistant": "Groq"}}', encoding="utf-8")
        (repo / "studio_config.json").write_text('{"temperature": 0.3}', encoding="utf-8")

    make_demo.build_demo_root("broadcast_studio", "broadcast_news_digest", mock=mock)

    questions = load_questions(root / "benchmark_questions/questions.example.json")
    assert len(questions) == 3
    config = json.loads((root / "studio_config.json").read_text(encoding="utf-8"))
    assert config["default_org"] == "broadcast_studio"
    assert config["temperature"] == (0.7 if mock else 0.3)
    assert config["user_context"]["enabled"] is True
    assert config["user_context"]["path"] == "user_context/my_context.md"
    rag = config["user_context"]["rag"]
    assert rag["enabled"] is True
    assert rag["corpus_dir"] == "user_context/corpus"
    assert rag["index_dir"] == "user_context/index"
    if mock:
        assert rag["top_k"] == 3
    mapping = json.loads((root / "organizations/broadcast_studio/model_mapping.json").read_text(encoding="utf-8"))
    assert mapping["midori"]["assistant"] == ("mock" if mock else "Groq")


def test_real_demo_requires_configured_model_mapping(demo_repo):
    with pytest.raises(FileNotFoundError, match="model_mapping.example.json"):
        make_demo.build_demo_root("broadcast_studio", "broadcast_news_digest")


def test_benchmark_completion_ignores_hidden_tab():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("Playwright Chromium がインストールされていません")
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(
                '<div hidden><p>✅ 完了しました</p></div>'
                '<div id="active" hidden><p>✅ 完了しました</p></div>'
                '<script>setTimeout(() => document.getElementById("active").hidden = false, 100)</script>'
            )
            make_demo.wait_for_benchmark_completion(page, timeout=3000)
            assert page.locator("#active").is_visible()
        finally:
            browser.close()
