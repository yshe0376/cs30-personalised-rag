"""The M8 page hosts the existing online learning workflow without paid calls."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "src/cs30/ui/qa_app.py"
ONLINE = "Online learning · textbook quizzes"


def test_online_mode_reports_missing_config_without_creating_runtime(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("CS30_LEARNING_CONFIG", str(tmp_path / "missing.toml"))
    app = AppTest.from_file(PAGE, default_timeout=30)
    app.session_state["qa-demo-settings"] = {
        "mode": ONLINE, "model": "openai/gpt-oss-20b", "retrieval": "hybrid",
    }
    app.run()
    assert not app.exception
    assert any("No local config" in item.value for item in app.error)
    assert "learning_runtime" not in app.session_state
    assert any("v3-mode-live" in item.value and "Online learning" in item.value
               for item in app.markdown)


def test_learning_entry_redirects_to_same_m8_page(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("CS30_LEARNING_CONFIG", str(tmp_path / "missing.toml"))
    app = AppTest.from_file(ROOT / "src/cs30/ui/learning_app.py", default_timeout=30).run()
    assert not app.exception
    assert app.session_state["qa-demo-settings"]["mode"] == ONLINE
    assert any("No local config" in item.value for item in app.error)


def test_online_mode_is_available_from_m8_mode_dialog(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("CS30_LEARNING_CONFIG", str(tmp_path / "missing.toml"))
    app = AppTest.from_file(PAGE, default_timeout=30).run()
    next(button for button in app.button if button.label == "Demo Mode").click().run()
    selector = next(item for item in app.selectbox if item.label == "Demo mode")
    assert ONLINE in selector.options
