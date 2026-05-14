"""cleanup_orphans.py - 清理 messages 表中 anchor_msg_id 已失联的孤儿行。

正常情况下不应有孤儿：硬删回合时会删除 anchor 与所有 version=0 子消息；
保留的是 version>=1 的旧版本，它们的 anchor_msg_id 仍指向同一 anchor msg_id（活跃组里的 user 或被推到旧版位的 user）。

可能产生孤儿的场景（兜底）：
1. 历史数据迁移过程中外键 SET NULL 触发；
2. 手动 SQL 操作误删了 anchor 行；
3. 旧版代码 bug。

策略：删除 anchor_msg_id IS NULL 的所有 message 行。
也可选地：清理 anchor_msg_id 指向的 msg_id 已不存在的行（更激进）。
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("cleanup_orphans")


def cleanup(db_path: Path, dry_run: bool = False, strict: bool = False) -> None:
    if not db_path.exists():
        logger.error("database not found: %s", db_path)
        sys.exit(2)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        # 1. anchor_msg_id IS NULL 的孤儿
        null_rows = conn.execute(
            "SELECT msg_id, sid, kind FROM messages WHERE anchor_msg_id IS NULL"
        ).fetchall()
        logger.info("found %d rows with anchor_msg_id IS NULL", len(null_rows))
        for r in null_rows:
            logger.debug("  null-anchor: msg_id=%s sid=%s kind=%s", *r)

        # 2. anchor_msg_id 指向不存在 msg_id 的孤儿（仅 strict 模式查）
        dangling_rows: list = []
        if strict:
            dangling_rows = conn.execute(
                """
                SELECT m.msg_id, m.sid, m.kind, m.anchor_msg_id
                FROM messages AS m
                LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                WHERE m.anchor_msg_id IS NOT NULL AND a.msg_id IS NULL
                """
            ).fetchall()
            logger.info("found %d rows pointing to non-existent anchor", len(dangling_rows))
            for r in dangling_rows:
                logger.debug("  dangling: msg_id=%s sid=%s kind=%s anchor=%s", *r)

        if dry_run:
            logger.info("dry-run: not deleting")
            return

        if not null_rows and not dangling_rows:
            logger.info("no orphans to clean")
            return

        conn.execute("BEGIN")
        cur = conn.execute("DELETE FROM messages WHERE anchor_msg_id IS NULL")
        n1 = cur.rowcount
        n2 = 0
        if strict:
            cur = conn.execute(
                """
                DELETE FROM messages WHERE msg_id IN (
                    SELECT m.msg_id FROM messages AS m
                    LEFT JOIN messages AS a ON m.anchor_msg_id = a.msg_id
                    WHERE m.anchor_msg_id IS NOT NULL AND a.msg_id IS NULL
                )
                """
            )
            n2 = cur.rowcount
        conn.commit()
        logger.info("cleaned %d null-anchor rows, %d dangling rows", n1, n2)
    except Exception:
        conn.rollback()
        logger.exception("cleanup failed; rolled back")
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete orphan rows from messages table")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("backend/data/project.db"),
        help="path to the SQLite database (default: backend/data/project.db)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also delete rows whose anchor_msg_id points to a non-existent msg_id",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    cleanup(args.db, dry_run=args.dry_run, strict=args.strict)


if __name__ == "__main__":
    main()
