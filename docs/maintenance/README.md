# 数据库与维护工具说明

本目录包含了项目维护相关的脚本说明，用于处理数据库迁移、结构同步以及冗余文件清理。

## 1. 数据库结构修复 (`fix_database.py`)

**脚本位置**：`scripts/fix_database.py`

### 功能描述
该脚本用于自动同步 SQLite 数据库结构与代码期望的最新 Schema。当原有数据库缺少表、索引或特定列时，脚本会进行增量补全。

### 核心特性
- **增量更新**：使用 `ALTER TABLE` 补充缺失列，不破坏现有数据。
- **默认值保障**：自动为新列配置兼容性默认值（如 `supports_vision` 默认为 0）。
- **性能优化**：自动检查并补全所有核心业务索引。

### 运行方式
```bash
uv run python scripts/fix_database.py
```

---

## 2. 综合清理助手 (`scripts/cleanup_orphans.py`)

**脚本位置**：`scripts/cleanup_orphans.py`

### 功能描述
用于定期清理系统中的冗余数据，保持数据库整洁并释放磁盘空间。

### 清理范围
1. **孤儿消息**：清理 `messages` 表中由于删除操作或异常导致的、失去回合锚点（Anchor）的消息行。
2. **附件去重与同步**：
   - 删除数据库中记录存在但物理文件已丢失的“死记录”。
   - 扫描 `data/` 目录，删除未被数据库引用的“孤儿文件”。
3. **失效技能**：清理 `community_skills` 表中指向不存在归档路径的记录。
4. **空目录清理**：递归删除 `data/` 下因项目/会话删除留下的空文件夹结构。

### 运行方式
**预览模式（推荐）**：
```bash
uv run python scripts/cleanup_orphans.py --dry-run
```

**正式清理**：
```bash
uv run python scripts/cleanup_orphans.py
```

**激进模式**：
```bash
uv run python scripts/cleanup_orphans.py --strict
```
*(注：`--strict` 会额外检查消息 ID 之间的软关联有效性)*
