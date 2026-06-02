"""cleanup_orphans.py - 综合清理脚本。

职责：
1. 清理消息孤儿（anchor_msg_id 失联）。
2. 清理附件孤儿：
   - 数据库记录存在但物理文件已丢失。
   - 物理文件存在但数据库无记录（且不属于系统预留文件）。
3. 清理社区技能孤儿：记录存在但归档文件夹不存在。
4. 清理空目录：递归清理 data/ 目录下无文件的冗余目录。
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

# 尝试从项目配置导入，若失败则使用硬编码兜底
try:
    from backend.config import DATABASE_PATH, BASE_DIR
except ImportError:
    DATABASE_PATH = "data/project.db"
    BASE_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("cleanup")


def cleanup_messages(conn: sqlite3.Connection, strict: bool = False) -> tuple[int, int]:
    """清理消息表中的孤儿行。"""
    # 1. anchor_msg_id IS NULL 的孤儿
    cur = conn.execute("DELETE FROM messages WHERE anchor_msg_id IS NULL")
    n1 = cur.rowcount

    # 2. anchor_msg_id 指向不存在 msg_id 的孤儿
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
    return n1, n2


def cleanup_attachments(conn: sqlite3.Connection, dry_run: bool = False) -> tuple[int, int]:
    """清理附件。"""
    # 1. 检查物理文件丢失的数据库记录
    rows = conn.execute("SELECT attachment_id, file_path FROM attachments").fetchall()
    missing_records = []
    for aid, rel_path in rows:
        abs_path = (BASE_DIR / rel_path).resolve()
        if not abs_path.exists():
            missing_records.append(aid)

    deleted_records = 0
    if missing_records:
        logger.warning("Found %d attachment records with missing files", len(missing_records))
        if not dry_run:
            placeholders = ",".join("?" * len(missing_records))
            cur = conn.execute(f"DELETE FROM attachments WHERE attachment_id IN ({placeholders})", missing_records)
            deleted_records = cur.rowcount

    # 2. 检查数据库未记录的物理文件（清理孤儿文件）
    # 逻辑：遍历 data/ 下的所有文件，除去 project.db 和 skills/，如果不在 attachments 表中则删除
    all_files_in_db = {row[0] for row in conn.execute("SELECT file_path FROM attachments").fetchall()}
    
    deleted_files = 0
    data_dir = (BASE_DIR / "data").resolve()
    for p in data_dir.rglob("*"):
        if not p.is_file():
            continue
        
        # 排除数据库文件和技能目录
        rel_path = p.relative_to(BASE_DIR).as_posix()
        if rel_path == "data/project.db" or rel_path.startswith("data/skills/"):
            continue
        
        if rel_path not in all_files_in_db:
            logger.info("Found orphan file: %s", rel_path)
            deleted_files += 1
            if not dry_run:
                p.unlink()

    return deleted_records, deleted_files


def cleanup_skills(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """清理社区技能孤儿记录。"""
    rows = conn.execute("SELECT id, archive_path FROM community_skills").fetchall()
    missing_skills = []
    for sid, rel_path in rows:
        abs_path = (BASE_DIR / rel_path).resolve()
        if not abs_path.exists():
            missing_skills.append(sid)

    deleted_skills = 0
    if missing_skills:
        logger.warning("Found %d community skill records with missing archives", len(missing_skills))
        if not dry_run:
            placeholders = ",".join("?" * len(missing_skills))
            cur = conn.execute(f"DELETE FROM community_skills WHERE id IN ({placeholders})", missing_skills)
            deleted_skills = cur.rowcount
    return deleted_skills


def cleanup_empty_dirs(root_dir: Path, dry_run: bool = False) -> int:
    """递归删除空目录。"""
    deleted_count = 0
    # 自底向上遍历
    for p in sorted(list(root_dir.rglob("*")), key=lambda x: len(x.parts), reverse=True):
        if p.is_dir() and not any(p.iterdir()):
            # 排除 data/ 根目录本身
            if p == root_dir:
                continue
            logger.info("Removing empty directory: %s", p.relative_to(BASE_DIR))
            deleted_count += 1
            if not dry_run:
                p.rmdir()
    return deleted_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Teachi Comprehensive Cleanup Script")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(DATABASE_PATH),
        help=f"path to the SQLite database (default: {DATABASE_PATH})",
    )
    parser.add_argument("--strict", action="store_true", help="strict message cleanup")
    parser.add_argument("--dry-run", action="store_true", help="show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    db_path = args.db.resolve()
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        sys.exit(1)

    logger.info("Starting cleanup (Target: %s, Dry Run: %s)", db_path, args.dry_run)
    
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    
    try:
        if not args.dry_run:
            conn.execute("BEGIN")

        # 1. 消息清理
        n1, n2 = cleanup_messages(conn, args.strict)
        logger.info("Messages: Cleaned %d null-anchor rows, %d dangling rows", n1, n2)

        # 2. 附件清理
        dr, df = cleanup_attachments(conn, args.dry_run)
        logger.info("Attachments: Deleted %d dangling records, %d orphan files", dr, df)

        # 3. 技能清理
        ds = cleanup_skills(conn, args.dry_run)
        logger.info("Community Skills: Deleted %d dangling records", ds)

        # 4. 空目录清理
        de = cleanup_empty_dirs(db_path.parent, args.dry_run)
        logger.info("Directories: Removed %d empty directories", de)

        if not args.dry_run:
            conn.commit()
            logger.info("Changes committed successfully.")
        else:
            logger.info("Dry run finished. No changes were made.")

    except Exception:
        if not args.dry_run:
            conn.rollback()
        logger.exception("Cleanup failed")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
