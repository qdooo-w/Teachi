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

---

## 3. 设置社区管理员 (`scripts/set_admin.py`)

**脚本位置**：`scripts/set_admin.py`

### 功能描述
根据用户邮箱在 SQLite 数据库中查找已有用户，并将 `users.role` 更新为 `admin`。社区管理员审核接口会读取该字段进行后端权限校验。

### 运行方式
使用默认 `DATABASE_PATH`：
```bash
uv run python scripts/set_admin.py user@example.com
```

指定数据库路径：
```bash
uv run python scripts/set_admin.py user@example.com --db data/project.db
```

### 输出与错误
- 成功：输出实际使用的数据库绝对路径、用户 UUID、用户名、邮箱，以及角色变化。
- 用户已是管理员：输出 `User is already admin`，退出码为 0。
- 邮箱不存在或数据库路径不存在：输出错误信息，退出码为 1。

### 注意事项
- 参数必须是已经注册用户的邮箱。
- 如果目标数据库缺少 `users.role` 字段，脚本会直接退出并提示可能传错了旧库路径，不会自动改动旧库结构。
- `--db` 路径相对于项目根目录解析。项目根目录下的新库通常是 `data/project.db`；`../data/project.db` 会指向父目录的另一个数据库。
- 如果用户已经打开前端页面，更新后需要刷新页面，让前端重新通过 `/auth/me` 读取最新 `role`。

---

## 4. 创建默认测试用户 (`scripts/add_user.py`)

**脚本位置**：`scripts/add_user.py`

### 功能描述
用于在当前 SQLite 数据库中快速创建一个本地测试用户。脚本会读取 `.env` 中的 `DATABASE_PATH`；如果未配置，则默认写入 `data/project.db`。

当前脚本内置创建的用户为：

| 字段 | 值 |
|---|---|
| 用户名 | `user` |
| 邮箱 | `user@example.com` |
| 密码 | `admin114514` |

### 运行方式
```bash
uv run python scripts/add_user.py
```

### 输出与错误
- 成功：输出数据库路径、用户 UUID、用户名和邮箱。
- 用户已存在：输出已存在用户的信息，不会重复创建。
- 创建失败：输出错误信息，退出码为 1。

### 常见流程
如果刚换了一个新数据库，可以按顺序初始化数据库、创建默认用户、设置社区管理员：

```bash
uv run python -m backend.db
uv run python scripts/add_user.py
uv run python scripts/set_admin.py user@example.com --db data/project.db
```

### 注意事项
- 该脚本当前不接受命令行参数；如需创建其他邮箱、用户名或密码，需要修改脚本末尾的 `username`、`email`、`password` 默认值，或通过前端注册。
- `set_admin.py --db` 的路径应指向同一个数据库。项目根目录下通常使用 `data/project.db`。
