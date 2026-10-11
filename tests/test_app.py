"""Smoke test for the Streamlit app: every clip renders without errors (no browser, no API calls)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def test_every_clip_renders_with_explanation_and_check():
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception
    options = list(app.sidebar.selectbox[0].options)
    assert len(options) >= 3

    for option in options:
        app.sidebar.selectbox[0].select(option).run()  # widgets are rebuilt on every run, so look it up again
        assert not app.exception, option
        texts = " ".join(m.value for m in app.markdown)
        assert "What happened" in texts and "Coach" in texts, option
        assert len(app.success) == 1 and "Checked: all" in app.success[0].value, option
