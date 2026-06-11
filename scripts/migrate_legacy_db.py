#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.db import DatabaseFacade

DEFAULT_SOURCE = PROJECT_ROOT.parent / "data" / "project.db"
DEFAULT_TARGET = PROJECT_ROOT / "data" / "project.migrated.db"

SKIPPED_TABLES = (
    "nonces",
    "community_skills",
    "community_skill_versions",
    "community_skill_likes",
    "community_skill_comments",
    "community_comment_likes",
    "community_comment_reports",
    "community_skill_contributors",
    "community_skill_admins",
    "user_library_skills",
    "skill_review_logs",
)


def _connect_source(path: Path) -> sqlite3.Connection:
    errors: list[str] = []
    for query in ("mode=ro", "immutable=1"):
        uri = f"{path.resolve().as_uri()}?{query}"
        try:
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            return conn
        except sqlite3.Error as exc:
            errors.append(f"{query}: {exc}")
    detail = "; ".join(errors)
    raise RuntimeError(f"failed to open source database read-only: {detail}")


def _connect_target(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f'SELECT COUNT(1) FROM "{table}"').fetchone()[0])


def _rows(conn: sqlite3.Connection, table: str, order_by: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    sql = f'SELECT * FROM "{table}"'
    if order_by and order_by in _columns(conn, table):
        sql += f' ORDER BY "{order_by}"'
    return [dict(row) for row in conn.execute(sql).fetchall()]


def _value(row: dict[str, Any], key: str, default: Any = None) -> Any:
    value = row.get(key, default)
    if value is None and default is not None:
        return default
    return value


def _insert_many(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    values: list[tuple[Any, ...]],
) -> int:
    if not values:
        return 0
    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
        values,
    )
    return len(values)


def _prepare_target(source: Path, target: Path, replace: bool) -> None:
    source_resolved = source.resolve()
    target_resolved = target.resolve()
    if source_resolved == target_resolved:
        raise ValueError("source and target database paths must be different")

    target.parent.mkdir(parents=True, exist_ok=True)
    existing = [target, target.with_name(f"{target.name}-wal"), target.with_name(f"{target.name}-shm")]
    if any(path.exists() for path in existing):
        if not replace:
            raise FileExistsError(f"target already exists: {target}")
        for path in existing:
            if path.exists():
                path.unlink()

    DatabaseFacade(str(target)).setup_database()


def migrate_legacy_database(source: Path, target: Path, *, replace: bool = False) -> dict[str, dict[str, int]]:
    if not source.exists():
        raise FileNotFoundError(f"source database does not exist: {source}")

    _prepare_target(source, target, replace)
    now = time.time()

    summary: dict[str, dict[str, int]] = {"copied": {}, "skipped": {}}
    source_conn = _connect_source(source)
    target_conn = _connect_target(target)

    try:
        with target_conn:
            users = _rows(source_conn, "users", "created_at")
            user_values = [
                (
                    row["uuid"],
                    row["username"],
                    row["email"],
                    row["password_hash"],
                    _value(row, "role", "user"),
                    _value(row, "self_description"),
                    _value(row, "major"),
                    _value(row, "head_file"),
                    row["created_at"],
                )
                for row in users
            ]
            summary["copied"]["users"] = _insert_many(
                target_conn,
                "users",
                (
                    "uuid",
                    "username",
                    "email",
                    "password_hash",
                    "role",
                    "self_description",
                    "major",
                    "head_file",
                    "created_at",
                ),
                user_values,
            )
            user_ids = {row["uuid"] for row in users}

            projects = [
                row
                for row in _rows(source_conn, "projects", "timestamp")
                if row.get("user_uuid") in user_ids
            ]
            project_values = [
                (
                    row["pid"],
                    row["projectname"],
                    row["user_uuid"],
                    row["timestamp"],
                    _value(row, "created_at", row["timestamp"]),
                )
                for row in projects
            ]
            summary["copied"]["projects"] = _insert_many(
                target_conn,
                "projects",
                ("pid", "projectname", "user_uuid", "timestamp", "created_at"),
                project_values,
            )
            project_ids = {row["pid"] for row in projects}

            sessions = [
                row
                for row in _rows(source_conn, "sessions", "timestamp")
                if row.get("pid") in project_ids
            ]
            session_values = [
                (
                    row["sid"],
                    row["pid"],
                    row["sessionname"],
                    row["timestamp"],
                    _value(row, "created_at", row["timestamp"]),
                )
                for row in sessions
            ]
            summary["copied"]["sessions"] = _insert_many(
                target_conn,
                "sessions",
                ("sid", "pid", "sessionname", "timestamp", "created_at"),
                session_values,
            )
            session_ids = {row["sid"] for row in sessions}

            messages = [
                row
                for row in _rows(source_conn, "messages", "timestamp")
                if row.get("sid") in session_ids
            ]
            message_values = [
                (
                    row["msg_id"],
                    row["sid"],
                    row["kind"],
                    row["raw_json"],
                    row["timestamp"],
                    None,
                    _value(row, "version", 0),
                    _value(row, "created_at", row["timestamp"]),
                )
                for row in messages
            ]
            summary["copied"]["messages"] = _insert_many(
                target_conn,
                "messages",
                (
                    "msg_id",
                    "sid",
                    "kind",
                    "raw_json",
                    "timestamp",
                    "anchor_msg_id",
                    "version",
                    "created_at",
                ),
                message_values,
            )
            message_ids = {row["msg_id"] for row in messages}
            message_anchors = [
                (row["anchor_msg_id"], row["msg_id"])
                for row in messages
                if row.get("anchor_msg_id") in message_ids
            ]
            target_conn.executemany(
                'UPDATE "messages" SET "anchor_msg_id" = ? WHERE "msg_id" = ?',
                message_anchors,
            )

            attachments = [
                row
                for row in _rows(source_conn, "attachments", "created_at")
                if row.get("sid") in session_ids and row.get("user_uuid") in user_ids
            ]
            attachment_values = [
                (
                    row["attachment_id"],
                    row["sid"],
                    row["user_uuid"],
                    row.get("anchor_msg_id") if row.get("anchor_msg_id") in message_ids else None,
                    row["original_filename"],
                    _value(row, "file_hash", ""),
                    row["file_path"],
                    row["mime_type"],
                    _value(row, "file_size", 0),
                    _value(row, "description"),
                    _value(row, "description_generated_at"),
                    _value(row, "created_at", now),
                )
                for row in attachments
            ]
            summary["copied"]["attachments"] = _insert_many(
                target_conn,
                "attachments",
                (
                    "attachment_id",
                    "sid",
                    "user_uuid",
                    "anchor_msg_id",
                    "original_filename",
                    "file_hash",
                    "file_path",
                    "mime_type",
                    "file_size",
                    "description",
                    "description_generated_at",
                    "created_at",
                ),
                attachment_values,
            )

            configs = [
                row
                for row in _rows(source_conn, "user_model_configs", "created_at")
                if row.get("user_uuid") in user_ids
            ]
            config_values = [
                (
                    row["config_id"],
                    row["user_uuid"],
                    row["config_name"],
                    _value(row, "api_key", ""),
                    _value(row, "base_url", ""),
                    _value(row, "model_name", ""),
                    _value(row, "user_instruction", ""),
                    _value(row, "temperature"),
                    _value(row, "max_tokens"),
                    _value(row, "is_active", 0),
                    _value(row, "supports_vision", 0),
                    _value(row, "created_at", now),
                    _value(row, "updated_at", _value(row, "created_at", now)),
                    _value(row, "top_p"),
                    _value(row, "frequency_penalty"),
                    _value(row, "presence_penalty"),
                    _value(row, "response_format"),
                )
                for row in configs
            ]
            summary["copied"]["user_model_configs"] = _insert_many(
                target_conn,
                "user_model_configs",
                (
                    "config_id",
                    "user_uuid",
                    "config_name",
                    "api_key",
                    "base_url",
                    "model_name",
                    "user_instruction",
                    "temperature",
                    "max_tokens",
                    "is_active",
                    "supports_vision",
                    "created_at",
                    "updated_at",
                    "top_p",
                    "frequency_penalty",
                    "presence_penalty",
                    "response_format",
                ),
                config_values,
            )

            preferences = [
                row
                for row in _rows(source_conn, "user_preferences", "updated_at")
                if row.get("user_uuid") in user_ids
            ]
            preference_values = [
                (
                    row["user_uuid"],
                    _value(row, "theme", "system"),
                    _value(row, "language", "zh-CN"),
                    _value(row, "font_size", "medium"),
                    _value(row, "code_line_numbers", 0),
                    _value(row, "enter_mode", "enter"),
                    _value(row, "loop_max_retries"),
                    _value(row, "test_connection_timeout"),
                    _value(row, "message_history_limit"),
                    _value(row, "updated_at", now),
                )
                for row in preferences
            ]
            summary["copied"]["user_preferences"] = _insert_many(
                target_conn,
                "user_preferences",
                (
                    "user_uuid",
                    "theme",
                    "language",
                    "font_size",
                    "code_line_numbers",
                    "enter_mode",
                    "loop_max_retries",
                    "test_connection_timeout",
                    "message_history_limit",
                    "updated_at",
                ),
                preference_values,
            )

            for table in SKIPPED_TABLES:
                summary["skipped"][table] = _count(source_conn, table)

        return summary
    finally:
        source_conn.close()
        target_conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate a legacy Learnova database into the current schema without community or skill data.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"legacy database path, default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help=f"new database path, default: {DEFAULT_TARGET}",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace the target database if it already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        summary = migrate_legacy_database(args.source, args.target, replace=args.replace)
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print("Copied rows:")
    for table, count in summary["copied"].items():
        print(f"  {table}: {count}")
    print("Skipped source rows:")
    for table, count in summary["skipped"].items():
        if count:
            print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
