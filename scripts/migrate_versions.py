"""migrate_versions.py - 把旧版 messages 表迁移到新模型。

旧模型字段：
    parent_msg_id  指向被重生成的旧 assistant 消息（仅 regenerate 产物有值）。
    version        从 1 起递增。
    is_latest      1 表示当前活跃，0 表示历史版本。

新模型字段（迁移目标）：
    anchor_msg_id  整个回合（turn）的锚点 msg_id —— 该回合首条 user 消息的自引用。
                   同一回合内 user / tool_call / tool_result / assistant / agent_response 共享。
    version        统一为 0（活跃版本）。所有历史版本（is_latest=0）将被删除。
    is_latest 列   废弃（迁移结束后整列丢弃）。

迁移步骤：
    1. 删除所有 is_latest=0 的历史版本消息。
    2. 按会话扫描剩余消息（按 timestamp 升序），把同回合的所有消息（含 user / tool_call /
       tool_result / assistant / agent_response）的 anchor 设为该回合首条 user 的 msg_id。
       该回合 user 自身 anchor_msg_id = msg_id（self-reference）。
    3. 把所有 version 写为 0。
    4. 重建 messages 表：列名 parent_msg_id → anchor_msg_id，去掉 is_latest 列。

幂等：脚本检测到表里已经是 anchor_msg_id 列且没有 is_latest 列时直接退出。
注意：删除历史版本不可逆，请先用 --dry-run 预览。
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("migrate_versions")


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _needs_migration(conn: sqlite3.Connection) -> bool:
    cols = _columns(conn, "messages")
    return "is_latest" in cols or "parent_msg_id" in cols and "anchor_msg_id" not in cols


def _delete_historical(conn: sqlite3.Connection) -> int:
    """物理删除所有 is_latest=0 的历史版本。"""
    cur = conn.execute("DELETE FROM messages WHERE is_latest = 0")
    return cur.rowcount


def _migrate_anchors(conn: sqlite3.Connection) -> int:
    """按会话扫描，把所有消息的 parent_msg_id 改写成回合 anchor，version 归 0。"""
    sids = [row[0] for row in conn.execute("SELECT sid FROM sessions").fetchall()]
    total = 0
    for sid in sids:
        rows = conn.execute(
            """
            SELECT msg_id, kind
            FROM messages
            WHERE sid = ?
            ORDER BY timestamp ASC, created_at ASC
            """,
            (sid,),
        ).fetchall()

        current_anchor: str | None = None
        for msg_id, kind in rows:
            if kind == "user":
                current_anchor = msg_id
            if current_anchor is None:
                # 异常数据：会话首条不是 user。退化为以自身为 anchor。
                current_anchor = msg_id
            conn.execute(
                "UPDATE messages SET parent_msg_id = ?, version = 0 WHERE msg_id = ?",
                (current_anchor, msg_id),
            )
            total += 1
    return total


def _rebuild_messages_table(conn: sqlite3.Connection) -> None:
    """重建表：列名 parent_msg_id → anchor_msg_id，去掉 is_latest，version 默认 0。"""
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN")
        conn.executescript(
            """
            CREATE TABLE messages_new (
                msg_id TEXT PRIMARY KEY,
                sid TEXT NOT NULL,
                kind TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                anchor_msg_id TEXT,
                version INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (sid) REFERENCES sessions(sid) ON DELETE CASCADE,
                FOREIGN KEY (anchor_msg_id) REFERENCES messages_new(msg_id) ON DELETE SET NULL
            );

            INSERT INTO messages_new (msg_id, sid, kind, raw_json, timestamp, anchor_msg_id, version, created_at)
            SELECT msg_id, sid, kind, raw_json, timestamp, parent_msg_id, version, created_at
            FROM messages;

            DROP TABLE messages;
            ALTER TABLE messages_new RENAME TO messages;
            """
        )
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def migrate(db_path: Path, dry_run: bool = False) -> None:
    if not db_path.exists():
        logger.error("database not found: %s", db_path)
        sys.exit(2)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        cols = _columns(conn, "messages")
        if "is_latest" not in cols and "anchor_msg_id" in cols:
            logger.info("messages table already on new schema; nothing to do.")
            return
        if "parent_msg_id" not in cols:
            logger.error("unexpected schema: neither parent_msg_id nor anchor_msg_id present")
            sys.exit(3)

        conn.execute("BEGIN")
        deleted = _delete_historical(conn) if "is_latest" in cols else 0
        logger.info("deleted %d historical (is_latest=0) messages", deleted)

        rewritten = _migrate_anchors(conn)
        logger.info("rewrote anchor/version for %d messages", rewritten)

        orphan = conn.execute(
            """
            SELECT m.msg_id FROM messages m
            LEFT JOIN sessions s ON m.sid = s.sid
            WHERE s.sid IS NULL
            """,
        ).fetchall()
        if orphan:
            logger.warning("found %d orphan messages (no matching session)", len(orphan))

        if dry_run:
            logger.info("dry-run: rolling back without rebuilding table")
            conn.execute("ROLLBACK")
            return

        conn.commit()
        _rebuild_messages_table(conn)
        logger.info("migration completed: column renamed to anchor_msg_id, is_latest dropped")
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        logger.exception("migration failed; rolled back")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate messages to anchor_msg_id + version=0 model")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("backend/data/project.db"),
        help="path to the SQLite database (default: backend/data/project.db)",
    )
    parser.add_argument("--dry-run", action="store_true", help="run UPDATEs in a transaction and rollback")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    migrate(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
