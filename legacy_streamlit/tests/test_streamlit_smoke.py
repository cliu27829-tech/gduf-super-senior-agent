from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_all_streamlit_pages_render_without_uncaught_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("GDUF_DB_PATH", str(tmp_path / "streamlit.db"))
    scripts = [Path("app.py"), *sorted(Path("pages").glob("*.py"))]
    assert len(scripts) == 7
    for script in scripts:
        app = AppTest.from_file(str(script.resolve()), default_timeout=20).run()
        assert not app.exception, f"{script}: {[item.value for item in app.exception]}"
