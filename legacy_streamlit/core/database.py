"""SQLite schema and connection helpers."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator


DEFAULT_DB_PATH = Path("data/gduf_agent.db")


class Database:
    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("GDUF_DB_PATH") or DEFAULT_DB_PATH
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(sql, parameters)
            return cursor.rowcount

    def query(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(sql, parameters).fetchone()
        return dict(row) if row else None

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS campus_locations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            campus TEXT NOT NULL,
            category TEXT NOT NULL,
            sub_category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            building TEXT NOT NULL DEFAULT '',
            floor TEXT NOT NULL DEFAULT '',
            area TEXT NOT NULL DEFAULT '',
            latitude REAL,
            longitude REAL,
            map_x REAL,
            map_y REAL,
            address TEXT NOT NULL DEFAULT '',
            opening_hours TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            services_json TEXT NOT NULL DEFAULT '[]',
            payment_methods_json TEXT NOT NULL DEFAULT '[]',
            navigation_url TEXT NOT NULL DEFAULT '',
            source_references_json TEXT NOT NULL DEFAULT '[]',
            verification_method TEXT NOT NULL DEFAULT 'unverified_seed',
            verified_at TEXT,
            valid_from TEXT,
            valid_until TEXT,
            freshness_status TEXT NOT NULL DEFAULT 'needs_verification',
            confidence REAL NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            data_status TEXT NOT NULL DEFAULT 'demo_fixture',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_locations_campus_category
            ON campus_locations(campus, category, is_active);

        CREATE TABLE IF NOT EXISTS location_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            FOREIGN KEY(location_id) REFERENCES campus_locations(id)
        );

        CREATE TABLE IF NOT EXISTS food_stalls (
            id TEXT PRIMARY KEY,
            canteen_id TEXT NOT NULL,
            name TEXT NOT NULL,
            campus TEXT NOT NULL,
            floor TEXT NOT NULL DEFAULT '',
            food_type TEXT NOT NULL DEFAULT '',
            common_items_json TEXT NOT NULL DEFAULT '[]',
            price_range TEXT NOT NULL DEFAULT '',
            meal_periods_json TEXT NOT NULL DEFAULT '[]',
            opening_hours TEXT NOT NULL DEFAULT '',
            payment_methods_json TEXT NOT NULL DEFAULT '[]',
            is_operating INTEGER,
            verified_at TEXT,
            source_references_json TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 0,
            data_status TEXT NOT NULL DEFAULT 'demo_fixture',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(canteen_id) REFERENCES campus_locations(id)
        );
        CREATE INDEX IF NOT EXISTS idx_stalls_campus_canteen
            ON food_stalls(campus, canteen_id, is_active);

        CREATE TABLE IF NOT EXISTS campus_maps (
            id TEXT PRIMARY KEY,
            campus TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_campus_maps_active
            ON campus_maps(campus, is_active, uploaded_at);

        CREATE TABLE IF NOT EXISTS location_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campus TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            publisher TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            fetched_at TEXT,
            is_official INTEGER NOT NULL DEFAULT 0,
            source_level INTEGER NOT NULL DEFAULT 8,
            source_status TEXT NOT NULL DEFAULT 'unverified',
            content_hash TEXT,
            cached_text TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS data_refresh_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campus TEXT NOT NULL,
            source_url TEXT NOT NULL,
            status TEXT NOT NULL,
            changed INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_location_feedback (
            id TEXT PRIMARY KEY,
            location_id TEXT,
            campus TEXT NOT NULL,
            user_id TEXT NOT NULL,
            feedback TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            FOREIGN KEY(location_id) REFERENCES campus_locations(id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            deadline TEXT,
            location TEXT NOT NULL DEFAULT '',
            materials_json TEXT NOT NULL DEFAULT '[]',
            submission_method TEXT NOT NULL DEFAULT '',
            source_text TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            needs_confirmation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_user_status_deadline
            ON tasks(user_id, status, deadline);
        """
        with self.transaction() as connection:
            connection.executescript(schema)
