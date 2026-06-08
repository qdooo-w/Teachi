#!/usr/bin/env python3
"""
社区技能测试数据脚本 — 直接操作 SQLite 数据库

用法:
  uv run python scripts/community_test.py add       # 添加 10 个测试技能
  uv run python scripts/community_test.py clean     # 删除所有社区数据
  uv run python scripts/community_test.py list      # 列出当前社区技能

数据库路径默认 backend/project.db，可用 DB_PATH 环境变量覆盖。
"""

import os
import sys
import uuid
import time
import random
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "data/project.db")

# ── 颜色 ──────────────────────────────────────────────────────────────────
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def log(msg: str) -> None:
    print(f"{GREEN}[INFO]{NC} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{NC} {msg}")


def err(msg: str) -> None:
    print(f"{RED}[ERR]{NC} {msg}")


def get_conn() -> sqlite3.Connection:
    """获取数据库连接，启用 WAL 模式和外键约束。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_first_user_uuid(conn: sqlite3.Connection) -> str | None:
    """获取数据库中第一个用户的 UUID."""
    row = conn.execute("SELECT uuid FROM users LIMIT 1").fetchone()
    if row is None:
        err("数据库中没有用户！请先注册一个账号。")
        return None
    return row[0]


def skills_data() -> list[dict]:
    """返回 10 个测试技能的元数据."""
    return [
        {
            "name": "code-reviewer",
            "display_name": "代码审查助手",
            "description": "自动审查代码，发现潜在 bug 和安全漏洞，生成详细审查报告",
            "readme_md": "# 代码审查助手\n\n一个智能代码审查工具，能够自动扫描代码库。\n\n## 功能\n\n- 静态代码分析\n- 安全漏洞检测\n- 代码风格检查\n- 生成详细报告\n\n## 使用方法\n\n1. 将代码文件放入工作目录\n2. 启动审查流程\n3. 查看生成的报告",
            "tags": '["ai","code","review"]',
        },
        {
            "name": "math-tutor",
            "display_name": "数学辅导老师",
            "description": "逐步解答数学问题，支持代数、几何、微积分等多个领域",
            "readme_md": "# 数学辅导老师\n\n互动式数学学习助手，适合中学生和大学生。\n\n## 覆盖领域\n\n- 代数方程\n- 几何证明\n- 微积分\n- 概率统计\n\n## 特色\n\n- 分步讲解\n- 可视化图表\n- 错题分析",
            "tags": '["education","math","tutorial"]',
        },
        {
            "name": "doc-translator",
            "display_name": "文档翻译器",
            "description": "将技术文档从英文翻译为中文，精准保留专业术语",
            "readme_md": "# 文档翻译器\n\n专业的技术文档翻译工具。\n\n## 支持格式\n\n- Markdown\n- reStructuredText\n- 纯文本\n\n## 翻译策略\n\n- 术语一致性校验\n- 代码块保持不变\n- 链接自动调整",
            "tags": '["translation","docs","i18n"]',
        },
        {
            "name": "api-generator",
            "display_name": "API 代码生成器",
            "description": "根据 OpenAPI 描述自动生成 RESTful API 服务端和客户端代码",
            "readme_md": "# API 代码生成器\n\n从 OpenAPI/Swagger 规范自动生成代码。\n\n## 支持语言\n\n- Python (FastAPI)\n- TypeScript (Axios)\n- Go (net/http)\n\n## 生成内容\n\n- 路由定义\n- 请求/响应模型\n- 参数校验\n- 错误处理",
            "tags": '["api","code","generator","openapi"]',
        },
        {
            "name": "data-visualizer",
            "display_name": "数据可视化工具",
            "description": "将 CSV/JSON 数据转换为交互式图表，支持柱状图、折线图、散点图等",
            "readme_md": "# 数据可视化工具\n\n快速将数据转换为美观的图表。\n\n## 图表类型\n\n- 柱状图 / 条形图\n- 折线图 / 面积图\n- 散点图 / 气泡图\n- 饼图 / 环形图\n\n## 数据源\n\n- CSV 文件\n- JSON 文件\n- 数据库查询结果",
            "tags": '["data","visualization","charts"]',
        },
        {
            "name": "git-helper",
            "display_name": "Git 操作助手",
            "description": "智能辅助 Git 操作，自动生成规范的 commit message，可视化分支管理",
            "readme_md": "# Git 操作助手\n\n让 Git 操作更简单、更规范。\n\n## 主要功能\n\n- 自动生成 Conventional Commits\n- 交互式 rebase 辅助\n- 冲突解决建议\n- 分支可视化",
            "tags": '["git","devtools","cli"]',
        },
        {
            "name": "sql-optimizer",
            "display_name": "SQL 优化器",
            "description": "分析 SQL 查询语句，识别性能瓶颈并给出索引和重写建议",
            "readme_md": "# SQL 优化器\n\n数据库查询性能分析工具。\n\n## 分析维度\n\n- 索引使用情况\n- JOIN 顺序优化\n- 子查询改写\n- 执行计划解读\n\n## 支持数据库\n\n- MySQL / MariaDB\n- PostgreSQL\n- SQLite",
            "tags": '["database","sql","optimization"]',
        },
        {
            "name": "test-writer",
            "display_name": "测试用例编写",
            "description": "根据源代码自动生成单元测试和集成测试代码，支持多种测试框架",
            "readme_md": "# 测试用例编写\n\n自动化测试生成工具。\n\n## 测试框架\n\n- pytest (Python)\n- Jest (JavaScript/TypeScript)\n- JUnit (Java)\n\n## 生成策略\n\n- 边界值测试\n- 异常路径覆盖\n- Mock 依赖自动生成",
            "tags": '["testing","code","quality"]',
        },
        {
            "name": "security-auditor",
            "display_name": "安全检查员",
            "description": "扫描代码中的安全漏洞（OWASP Top 10），生成修复建议和安全报告",
            "readme_md": "# 安全检查员\n\n代码安全审计工具。\n\n## 检测范围\n\n- SQL 注入\n- XSS 跨站脚本\n- CSRF 防护\n- 敏感信息泄露\n- 依赖漏洞\n\n## 输出格式\n\n- 风险等级分类\n- 漏洞详情说明\n- 修复代码示例",
            "tags": '["security","audit","owasp"]',
        },
        {
            "name": "note-organizer",
            "display_name": "笔记整理助手",
            "description": "将碎片化笔记智能整理为结构化知识库，自动提取标签和关联",
            "readme_md": "# 笔记整理助手\n\n知识管理工具，让笔记更有条理。\n\n## 整理功能\n\n- 自动分类归档\n- 关键词提取\n- 关联笔记推荐\n- 思维导图生成\n\n## 输入格式\n\n- Markdown\n- 纯文本\n- 语音转文字",
            "tags": '["productivity","notes","knowledge"]',
        },
        {
            "name": "prompt-engineer",
            "display_name": "提示词工程师",
            "description": "帮助用户优化和调试 AI 提示词，提供多种提示词模板和策略",
            "readme_md": "# 提示词工程师\n\n专业 Prompt Engineering 助手。\n\n## 核心功能\n\n- 提示词优化建议\n- 模板库检索\n- 多模型适配\n- A/B 测试对比\n\n## 适用场景\n\n- 文本生成\n- 代码辅助\n- 数据分析\n- 创意写作",
            "tags": '["ai","prompt","engineering"]',
        },
        {
            "name": "meeting-minutes",
            "display_name": "会议纪要生成器",
            "description": "根据会议录音或文字记录自动生成结构化会议纪要，提取行动项和决策点",
            "readme_md": "# 会议纪要生成器\n\n高效会议管理工具。\n\n## 输出内容\n\n- 会议摘要\n- 讨论要点\n- 决策记录\n- 行动项（含责任人和截止日期）\n\n## 输入方式\n\n- 录音文件\n- 实时转写文本\n- 会议笔记",
            "tags": '["productivity","meeting","notes"]',
        },
        {
            "name": "ui-mockup-builder",
            "display_name": "界面原型生成器",
            "description": "快速生成 UI 线框图和原型描述，支持多种设计风格和组件库",
            "readme_md": "# 界面原型生成器\n\n设计到代码的桥梁。\n\n## 输出格式\n\n- ASCII 线框图\n- HTML/CSS 原型\n- 组件规格说明\n\n## 支持风格\n\n- Material Design\n- Minimalism\n- Glassmorphism\n- Brutalism",
            "tags": '["design","ui","prototype"]',
        },
        {
            "name": "data-cleaner",
            "display_name": "数据清洗助手",
            "description": "自动检测和处理数据中的缺失值、异常值和重复项，标准化数据格式",
            "readme_md": "# 数据清洗助手\n\n让脏数据变得整洁。\n\n## 处理能力\n\n- 缺失值填充策略\n- 异常值检测与处理\n- 数据类型转换\n- 去重与合并\n\n## 数据格式\n\n- CSV / TSV\n- JSON / JSONL\n- Excel\n- 数据库表",
            "tags": '["data","cleaning","etl"]',
        },
        {
            "name": "regex-wizard",
            "display_name": "正则表达式向导",
            "description": "交互式构建和解释正则表达式，支持多种编程语言的正则方言",
            "readme_md": "# 正则表达式向导\n\n告别正则调试的痛苦。\n\n## 功能\n\n- 自然语言描述转正则\n- 正则可视化\n- 实时匹配测试\n- 多语言转译（Python/JS/Java/Go）\n\n## 常用模板\n\n- 邮箱 / URL / IP 地址\n- 手机号 / 身份证\n- 日期格式",
            "tags": '["regex","devtools","utility"]',
        },
        {
            "name": "env-manager",
            "display_name": "环境配置管家",
            "description": "管理开发环境配置文件，自动检测环境变量冲突和缺失",
            "readme_md": "# 环境配置管家\n\n告别 `.env.example` 和实际配置不一致的问题。\n\n## 核心功能\n\n- 环境变量冲突检测\n- 多环境配置对比\n- 自动生成配置文档\n- 敏感信息泄露扫描",
            "tags": '["devops","config","utility"]',
        },
        {
            "name": "image-describer",
            "display_name": "图片内容描述器",
            "description": "为图片生成细致的中文描述，支持无障碍场景的内容替代文本",
            "readme_md": "# 图片内容描述器\n\n为每一张图片讲好故事。\n\n## 输出类型\n\n- 简明 Alt Text（无障碍）\n- 详细内容描述\n- 技术图表解读\n- 场景分析\n\n## 适用图片\n\n- 照片 / 截图\n- 数据图表\n- 流程图\n- 插画 / 海报",
            "tags": '["vision","accessibility","content"]',
        },
        {
            "name": "changelog-writer",
            "display_name": "更新日志撰写器",
            "description": "根据 Git 提交记录自动生成规范的 CHANGELOG，遵循 Keep a Changelog 格式",
            "readme_md": "# 更新日志撰写器\n\nKeep a Changelog 自动生成工具。\n\n## 分类规则\n\n- Added 新增功能\n- Changed 功能变更\n- Deprecated 即将废弃\n- Removed 已移除\n- Fixed 问题修复\n- Security 安全修复\n\n## 输入\n\n- Git log / diff\n- Issue / PR 列表",
            "tags": '["git","docs","automation"]',
        },
        {
            "name": "benchmark-runner",
            "display_name": "性能基准测试器",
            "description": "为代码片段运行性能基准测试，对比不同实现方案的执行效率",
            "readme_md": "# 性能基准测试器\n\n科学衡量代码性能。\n\n## 测试维度\n\n- 执行时间\n- 内存占用\n- CPU 利用率\n- IO 吞吐量\n\n## 报告内容\n\n- 多方案对比\n- 统计显著性\n- 可视化图表\n- 优化建议",
            "tags": '["performance","benchmark","testing"]',
        },
        {
            "name": "error-decoder",
            "display_name": "报错信息解读器",
            "description": "解读各类编程语言的报错信息，用通俗语言解释并提供修复方案",
            "readme_md": "# 报错信息解读器\n\n不再对着红色报错发呆。\n\n## 支持语言\n\n- Python / JavaScript / TypeScript\n- Rust / Go / C++\n- Java / Kotlin\n- Shell / SQL\n\n## 解读内容\n\n- 错误原因分析\n- 修复步骤\n- 预防建议\n- 相关文档链接",
            "tags": '["debugging","devtools","learning"]',
        },
    ]


def add_skills() -> None:
    """向数据库插入 10 个测试技能。"""
    conn = get_conn()
    try:
        owner_uuid = get_first_user_uuid(conn)
        if not owner_uuid:
            sys.exit(1)

        log(f"使用用户: {owner_uuid}")

        skipped = 0
        added = 0
        for skill in skills_data():
            # 检查是否已存在同名技能
            existing = conn.execute(
                "SELECT id FROM community_skills WHERE name = ?", (skill["name"],)
            ).fetchone()
            if existing:
                warn(f"  跳过 {skill['display_name']} ({skill['name']}) — 已存在")
                skipped += 1
                continue

            skill_id = str(uuid.uuid4())
            version_id = str(uuid.uuid4())
            now = time.time()
            # 让每个技能的创建时间略有差异
            created_at = now - random.randint(0, 86400 * 7)  # 最近一周内
            updated_at = created_at + random.randint(3600, 86400 * 3)
            size_bytes = random.randint(2048, 51200)
            downloads = random.randint(0, 500)
            likes = random.randint(0, 200)
            version = "1.0.0"

            admin_uuids = f'["{owner_uuid}"]'
            archive_path = f"archived_skill/{skill_id}/{version}"

            conn.execute(
                """INSERT INTO community_skills
                   (id, owner_uuid, name, display_name, description,
                    admin_uuids, likes, downloads, latest_version,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill_id,
                    owner_uuid,
                    skill["name"],
                    skill["display_name"],
                    skill["description"],
                    admin_uuids,
                    likes,
                    downloads,
                    version,
                    created_at,
                    updated_at,
                ),
            )

            conn.execute(
                """INSERT INTO community_skill_versions
                   (id, skill_id, version, readme_md, changelog, tags,
                    archive_path, size_bytes, downloads, status, submitted_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    skill_id,
                    version,
                    skill["readme_md"],
                    "初始版本发布",
                    skill["tags"],
                    archive_path,
                    size_bytes,
                    downloads,
                    "APPROVED",
                    owner_uuid,
                    created_at,
                ),
            )

            conn.execute(
                """INSERT OR IGNORE INTO community_skill_admins
                   (skill_id, user_uuid, created_at)
                   VALUES (?, ?, ?)""",
                (skill_id, owner_uuid, created_at),
            )

            added += 1
            log(f"  ✓ {skill['display_name']} ({skill['name']})  id={skill_id}")

        conn.commit()
        msg = f"完成！新增 {added} 个技能"
        if skipped > 0:
            msg += f"，跳过 {skipped} 个已存在"
        log(msg)
    finally:
        conn.close()


def clean_skills() -> None:
    """清空所有社区相关数据。"""
    conn = get_conn()
    try:
        tables = [
            "community_comment_reports",
            "community_comment_likes",
            "community_skill_comments",
            "community_skill_likes",
            "community_skill_contributors",
            "community_skill_admins",
            "skill_review_logs",
            "community_skill_versions",
            "community_skills",
        ]

        for table in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            conn.execute(f"DELETE FROM {table}")
            if count > 0:
                log(f"  ✓ {table}: 删除 {count} 条")

        conn.commit()
        log("完成！所有社区数据已清空")
    finally:
        conn.close()


def list_skills() -> None:
    """列出当前数据库中的社区技能。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT s.id, s.name, s.display_name, s.likes, s.downloads, s.latest_version,
                      v.status, s.created_at
               FROM community_skills s
               LEFT JOIN community_skill_versions v ON s.id = v.skill_id
               ORDER BY s.created_at DESC"""
        ).fetchall()

        if not rows:
            log("当前没有社区技能")
            return

        print(f"\n{'ID':<38} {'名称':<16} {'版本':<8} {'状态':<16} {'点赞':<6} {'下载':<6}")
        print("-" * 100)
        for r in rows:
            skill_id, name, display, likes, downloads, version, status, _ = r
            label = display or name
            print(
                f"{skill_id:<38} {label:<16} {version or '-':<8}"
                f" {status or '-':<16} {likes:<6} {downloads:<6}"
            )

        print(f"\n共 {len(rows)} 个技能\n")
    finally:
        conn.close()


def main() -> None:
    if not os.path.exists(DB_PATH):
        err(f"数据库文件不存在: {DB_PATH}")
        err("请先启动一次后端服务以初始化数据库，或用 DB_PATH 指定正确的路径。")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    force = "--force" in sys.argv or "-f" in sys.argv

    if cmd == "add":
        if force:
            log("--force：先清空已有数据...")
            conn = get_conn()
            try:
                for t in ["community_comment_reports","community_comment_likes","community_skill_comments",
                          "community_skill_likes","community_skill_contributors","community_skill_admins",
                          "skill_review_logs","community_skill_versions","community_skills"]:
                    conn.execute(f"DELETE FROM {t}")
                conn.commit()
            finally:
                conn.close()
        add_skills()
    elif cmd == "clean":
        if force:
            clean_skills()
        else:
            warn("即将清空所有社区数据（技能、版本、评论、点赞、举报等）！")
            confirm = input("确认清空？(输入 yes 继续): ").strip()
            if confirm == "yes":
                clean_skills()
            else:
                log("已取消")
    elif cmd == "list":
        list_skills()
    else:
        print("用法: uv run python scripts/community_test.py {add|clean|list}")
        print()
        print("  add    - 添加 10 个测试技能（含 README、版本、随机点赞/下载数）")
        print("  clean  - 清空所有社区数据（需要输入 yes 确认）")
        print("  list   - 列出当前社区技能")
        print()
        print("环境变量:")
        print("  DB_PATH  数据库路径 (默认 backend/project.db)")
        sys.exit(1)


if __name__ == "__main__":
    main()
