#!/usr/bin/env python3
"""
向默认测试用户仓库中写入测试技能数据。

用法:
    python scripts/seed_library.py              # 使用数据库中第一个用户
    python scripts/seed_library.py <user_uuid>  # 指定用户 UUID

每运行一次写入 8 个测试技能，涵盖不同标签、来源（本地收集/来自社区）。
"""

import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

# 项目根目录（脚本位于 scripts/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "project.db"))
DATA_DIR = PROJECT_ROOT / "data"


def get_default_user() -> str | None:
    """获取数据库中的第一个用户 UUID。"""
    if not Path(DATABASE_PATH).exists():
        print(f"❌ 数据库不存在: {DATABASE_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT uuid FROM users LIMIT 1").fetchone()
    conn.close()
    return row["uuid"] if row else None


# ── 测试技能模板 ────────────────────────────────────────────────────────────

SEED_SKILLS = [
    {
        "name": "test-code-review",
        "display_name": "代码审查助手",
        "description": "自动审查代码风格、潜在 bug 和安全漏洞，支持 Python / TypeScript / Go。",
        "readme_md": "# 代码审查助手\n\n在提交 PR 前运行审查，识别常见问题。\n\n## 使用方法\n\n在对话中粘贴代码，助手会给出改进建议。",
        "tags": '["code", "review", "productivity"]',
        "version": "1.2.0",
        "changelog": "新增 Go 语言支持",
        "community_skill_id": None,
    },
    {
        "name": "test-doc-generator",
        "display_name": "文档生成器",
        "description": "根据代码自动生成 API 文档、README 和变更日志。",
        "readme_md": "# 文档生成器\n\n扫描代码仓库并生成结构化文档。\n\n支持 JSDoc / docstring 解析。",
        "tags": '["docs", "productivity"]',
        "version": "1.0.0",
        "changelog": "Initial collect",
        "community_skill_id": None,
    },
    {
        "name": "test-sql-optimizer",
        "display_name": "SQL 优化顾问",
        "description": "分析 SQL 查询性能，给出索引建议和重写方案。",
        "readme_md": "# SQL 优化顾问\n\n输入你的 SQL 查询和表结构，得到优化建议。",
        "tags": '["database", "sql", "performance"]',
        "version": "2.0.1",
        "changelog": "修复 PostgreSQL 兼容性问题",
        "community_skill_id": "fake-community-id-001",
    },
    {
        "name": "test-api-tester",
        "display_name": "API 测试工坊",
        "description": "快速生成 RESTful API 测试用例，支持 OpenAPI/Swagger 导入。",
        "readme_md": "# API 测试工坊\n\n导入 OpenAPI 规范即可生成测试套件。",
        "tags": '["api", "testing"]',
        "version": "1.0.0",
        "changelog": "Fork",
        "community_skill_id": "fake-community-id-002",
    },
    {
        "name": "test-ui-preview",
        "display_name": "UI 预览器",
        "description": "实时预览 HTML/CSS/JS 片段，支持 Tailwind CSS 和 Vue 组件。",
        "readme_md": "# UI 预览器\n\n粘贴前端代码即可在嵌入式浏览器中预览效果。",
        "tags": '["frontend", "ui", "preview"]',
        "version": "0.9.0",
        "changelog": "Initial collect",
        "community_skill_id": None,
    },
    {
        "name": "test-data-visualizer",
        "display_name": "数据可视化",
        "description": "将 CSV/JSON 数据转换为交互式图表，支持折线图、柱状图、散点图等。",
        "readme_md": "# 数据可视化\n\n上传数据文件，选择图表类型，生成可视化结果。",
        "tags": '["data", "visualization", "charts"]',
        "version": "1.5.0",
        "changelog": "新增散点图和热力图支持",
        "community_skill_id": None,
    },
    {
        "name": "test-translator",
        "display_name": "多语言翻译",
        "description": "支持中英日韩等 20+ 语言的文档和代码注释翻译。",
        "readme_md": "# 多语言翻译\n\n保持代码结构不变，仅翻译注释和文档字符串。",
        "tags": '["i18n", "translation"]',
        "version": "1.0.0",
        "changelog": "Initial collect",
        "community_skill_id": None,
    },
    {
        "name": "test-deploy-helper",
        "display_name": "部署助手",
        "description": "一键生成 Dockerfile、docker-compose 和 CI/CD 配置。",
        "readme_md": "# 部署助手\n\n根据项目类型自动生成容器化部署配置。\n\n支持 Node.js / Python / Go / Rust。",
        "tags": '["devops", "deploy", "docker"]',
        "version": "2.1.0",
        "changelog": "新增 Rust 项目支持，优化构建缓存",
        "community_skill_id": "fake-community-id-003",
    },
]


def create_skill_dir(library_dir: Path, name: str) -> None:
    """创建技能文件目录结构。"""
    skill_dir = library_dir / "skill"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # 写入 SKILL.md
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: Test skill\n---\n\n# {name}\n\nThis is a seed test skill.\n",
        encoding="utf-8",
    )


def seed(user_uuid: str) -> None:
    """向指定用户仓库写入测试数据。"""
    if not Path(DATABASE_PATH).exists():
        print(f"❌ 数据库不存在: {DATABASE_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    # 验证用户存在
    user = conn.execute("SELECT uuid, username FROM users WHERE uuid = ?", (user_uuid,)).fetchone()
    if not user:
        print(f"❌ 用户 {user_uuid} 不存在")
        conn.close()
        sys.exit(1)

    print(f"📦 向用户 {user['username']} ({user_uuid}) 写入测试技能...")

    now_ts = time.time()
    user_library_dir = DATA_DIR / user_uuid / "library"
    added = 0

    for skill in SEED_SKILLS:
        library_id = str(uuid.uuid4())

        # 检查是否已存在同名技能
        existing = conn.execute(
            "SELECT id FROM user_library_skills WHERE user_uuid = ? AND name = ?",
            (user_uuid, skill["name"]),
        ).fetchone()
        if existing:
            print(f"  ⏭  跳过已存在: {skill['name']}")
            continue

        # 创建文件目录
        library_dir = user_library_dir / library_id
        create_skill_dir(library_dir, skill["name"])

        # 写入 README.md
        (library_dir / "README.md").write_text(skill["readme_md"], encoding="utf-8")

        # 计算目录大小
        total_size = sum(
            f.stat().st_size for f in library_dir.rglob("*") if f.is_file()
        )

        local_path = f"data/{user_uuid}/library/{library_id}"

        # 写入数据库
        conn.execute(
            """
            INSERT INTO user_library_skills
            (id, user_uuid, name, display_name, description, readme_md, tags,
             version, changelog, community_skill_id, local_path, size_bytes,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                library_id,
                user_uuid,
                skill["name"],
                skill["display_name"],
                skill["description"],
                skill["readme_md"],
                skill["tags"],
                skill["version"],
                skill["changelog"],
                skill["community_skill_id"],
                local_path,
                total_size,
                now_ts,
                now_ts,
            ),
        )
        print(f"  ✅ {skill['name']} (v{skill['version']})")
        added += 1

    conn.commit()
    conn.close()
    print(f"\n🎉 完成！写入 {added} 个测试技能。")


if __name__ == "__main__":
    user_uuid = sys.argv[1] if len(sys.argv) > 1 else get_default_user()
    if not user_uuid:
        print("❌ 数据库中没有用户。请先注册一个账号，或通过命令行参数指定 user_uuid。")
        print("   用法: python scripts/seed_library.py <user_uuid>")
        sys.exit(1)

    seed(user_uuid)
