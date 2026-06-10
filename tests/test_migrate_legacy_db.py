from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.migrate_legacy_db import migrate_legacy_database


def _create_legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE users (
                uuid TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE projects (
                pid TEXT PRIMARY KEY,
                projectname TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE sessions (
                sid TEXT PRIMARY KEY,
                pid TEXT NOT NULL,
                sessionname TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE messages (
                msg_id TEXT PRIMARY KEY,
                sid TEXT NOT NULL,
                kind TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                anchor_msg_id TEXT,
                version INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE TABLE attachments (
                attachment_id TEXT PRIMARY KEY,
                sid TEXT NOT NULL,
                user_uuid TEXT NOT NULL,
                anchor_msg_id TEXT,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                description TEXT,
                description_generated_at REAL,
                created_at REAL NOT NULL
            );
            CREATE TABLE user_model_configs (
                config_id TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                config_name TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT '',
                user_instruction TEXT NOT NULL DEFAULT '',
                temperature REAL,
                max_tokens INTEGER,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE user_preferences (
                user_uuid TEXT PRIMARY KEY,
                theme TEXT NOT NULL DEFAULT 'system',
                language TEXT NOT NULL DEFAULT 'zh-CN',
                font_size TEXT NOT NULL DEFAULT 'medium',
                code_line_numbers INTEGER NOT NULL DEFAULT 0,
                enter_mode TEXT NOT NULL DEFAULT 'enter',
                loop_max_retries INTEGER,
                test_connection_timeout INTEGER,
                message_history_limit INTEGER,
                updated_at REAL NOT NULL
            );
            CREATE TABLE nonces (
                nonce TEXT PRIMARY KEY,
                user_uuid TEXT NOT NULL,
                timestamp REAL NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE community_skills (
                id TEXT PRIMARY KEY,
                owner_uuid TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                description TEXT NOT NULL,
                archive_path TEXT NOT NULL,
                license TEXT,
                compatibility TEXT,
                size_bytes INTEGER NOT NULL,
                downloads INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
            ("user-1", "Alice", "alice@example.com", "hash", 100.0),
        )
        conn.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
            ("project-1", "Math", "user-1", 101.0, 101.0),
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            ("session-1", "project-1", "Algebra", 102.0, 102.0),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-1", "session-1", "request", "{}", 103.0, None, 0, 103.0),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("msg-2", "session-1", "response", "{}", 104.0, "msg-1", 0, 104.0),
        )
        conn.execute(
            "INSERT INTO attachments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "attachment-1",
                "session-1",
                "user-1",
                "msg-2",
                "note.txt",
                "data/user-1/project-1/session-1/note.txt",
                "text/plain",
                "note",
                105.0,
                105.0,
            ),
        )
        conn.execute(
            "INSERT INTO user_model_configs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "config-1",
                "user-1",
                "Default",
                "key",
                "https://example.test",
                "model",
                "",
                None,
                None,
                1,
                106.0,
                106.0,
            ),
        )
        conn.execute(
            "INSERT INTO user_preferences VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("user-1", "dark", "zh-CN", "medium", 1, "ctrl_enter", None, None, 20, 107.0),
        )
        conn.execute(
            "INSERT INTO nonces VALUES (?, ?, ?, ?)",
            ("nonce-1", "user-1", 108.0, 108.0),
        )
        conn.execute(
            "INSERT INTO community_skills VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "skill-1",
                "user-1",
                "legacy-skill",
                "Legacy Skill",
                "drop me",
                "archived_skill/skill-1",
                None,
                None,
                10,
                1,
                109.0,
                109.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_migrate_legacy_database_keeps_user_conversation_data_only(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "new.db"
    _create_legacy_db(source)

    summary = migrate_legacy_database(source, target)

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        assert summary["copied"]["users"] == 1
        assert summary["copied"]["messages"] == 2
        assert summary["skipped"]["community_skills"] == 1
        assert summary["skipped"]["nonces"] == 1

        user = conn.execute("SELECT * FROM users WHERE uuid = 'user-1'").fetchone()
        assert user["role"] == "user"
        assert user["self_description"] is None
        assert user["major"] is None
        assert user["head_file"] is None

        message = conn.execute("SELECT * FROM messages WHERE msg_id = 'msg-2'").fetchone()
        assert message["anchor_msg_id"] == "msg-1"

        attachment = conn.execute("SELECT * FROM attachments WHERE attachment_id = 'attachment-1'").fetchone()
        assert attachment["anchor_msg_id"] == "msg-2"
        assert attachment["file_hash"] == ""
        assert attachment["file_size"] == 0

        config = conn.execute("SELECT * FROM user_model_configs WHERE config_id = 'config-1'").fetchone()
        assert config["supports_vision"] == 0
        assert config["top_p"] is None
        assert config["frequency_penalty"] is None
        assert config["presence_penalty"] is None
        assert config["response_format"] is None

        preferences = conn.execute("SELECT * FROM user_preferences WHERE user_uuid = 'user-1'").fetchone()
        assert preferences["enter_mode"] == "ctrl_enter"
        assert preferences["message_history_limit"] == 20

        assert conn.execute("SELECT COUNT(1) FROM community_skills").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(1) FROM user_library_skills").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(1) FROM nonces").fetchone()[0] == 0
    finally:
        conn.close()
