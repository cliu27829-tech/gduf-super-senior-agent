from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_empty_database_migrates_to_head(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh.db"
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
        "ENVIRONMENT": "test",
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "true",
        "DEEPSEEK_API_KEY": "migration-test-placeholder",
        "DEEPSEEK_BASE_URL": "http://127.0.0.1:1",
        "DEEPSEEK_MODEL": "deepseek-v4-flash",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert revision == ("20260809_09",)
    assert {"agent_runs", "agent_run_steps"}.issubset(tables)
