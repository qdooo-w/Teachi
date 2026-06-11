#!/usr/bin/env python3
"""
清除由 seed_library.py 写入的测试技能数据。

用法:
    python scripts/clean_library.py              # 清除第一个用户的所有测试技能
    python scripts/clean_library.py <user_uuid>  # 清除指定用户的测试技能
    python scripts/clean_library.py --all        # 清除所有用户的测试技能

只清除 name 以 "test-" 开头的技能（DB 记录 + 文件目录）。
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "project.db"))
DATA_DIR = PROJECT_ROOT / "data"

TEST_PREFIX = "test-"


def get_default_user() -> str | None:
    if not Path(DATABASE_PATH).exists():
        print(f"❌ 数据库不存在: {DATABASE_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT uuid FROM users LIMIT 1").fetchone()
    conn.close()
    return row["uuid"] if row else None


def clean_user(user_uuid: str) -> int:
    """清除指定用户的测试技能，返回删除数量。"""
    if not Path(DATABASE_PATH).exists():
        print(f"❌ 数据库不存在: {DATABASE_PATH}")
        return 0

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    # 查找测试技能
    rows = conn.execute(
        "SELECT id, name, local_path FROM user_library_skills WHERE user_uuid = ? AND name LIKE ?",
        (user_uuid, f"{TEST_PREFIX}%"),
    ).fetchall()

    if not rows:
        conn.close()
        print(f"  没有测试技能。")
        return 0

    user = conn.execute("SELECT username FROM users WHERE uuid = ?", (user_uuid,)).fetchone()
    username = user["username"] if user else user_uuid
    print(f"🧹 清除用户 {username} 的测试技能:")

    for row in rows:
        skill_id = row["id"]
        name = row["name"]
        local_path = row["local_path"]

        # 删除数据库记录
        conn.execute("DELETE FROM user_library_skills WHERE id = ?", (skill_id,))

        # 删除文件目录（local_path 如 "data/{uuid}/library/{id}" 相对于项目根目录）
        dir_path = PROJECT_ROOT / local_path if not Path(local_path).is_absolute() else Path(local_path)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"  🗑  {name} (DB + 文件)")
        else:
            print(f"  🗑  {name} (仅 DB，文件不存在)")

    conn.commit()
    conn.close()
    return len(rows)


def clean_all() -> int:
    """清除所有用户的测试技能。"""
    if not Path(DATABASE_PATH).exists():
        print(f"❌ 数据库不存在: {DATABASE_PATH}")
        return 0

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT uuid FROM users").fetchall()
    conn.close()

    total = 0
    for u in users:
        total += clean_user(u["uuid"])
    return total


if __name__ == "__main__":
    if "--all" in sys.argv:
        count = clean_all()
        print(f"\n🎉 完成！共清除 {count} 个测试技能。")
    elif len(sys.argv) > 1:
        user_uuid = sys.argv[1]
        count = clean_user(user_uuid)
        print(f"\n🎉 完成！清除 {count} 个测试技能。")
    else:
        user_uuid = get_default_user()
        if not user_uuid:
            print("❌ 数据库中没有用户。")
            print("   用法: python scripts/clean_library.py [<user_uuid>|--all]")
            sys.exit(1)
        count = clean_user(user_uuid)
        print(f"\n🎉 完成！清除 {count} 个测试技能。")
