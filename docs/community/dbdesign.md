# 社区 & 仓库 数据库 + API 设计文档

## 术语说明

| 术语 | 含义 |
|---|---|
| **社区 (Community)** | 公开的技能市场，所有用户可浏览/安装 |
| **仓库 (Library)** | 用户私有的技能仓库，每次从运行层上传就是一个独立 skill 条目 |
| **运行层 (Runtime)** | 项目级/用户级 skill 文件夹（`data/{uuid}/skills/`），纯文件系统，无 DB 记录 |
| **收集面板 (Collection Panel)** | 从运行层/仓库收集 skill 元数据的表单 UI |

---

## 数据流与 UUID 继承模型

```
运行层 (文件系统，无 DB 记录)
   │ ← 收集面板：读取 SKILL.md，填表单，每次上传都是一个新 skill 条目
   ▼
仓库 (user_library_skills，每条独立)
   │ ← 收集面板：继承仓库数据，填表单提交审核
   ▼
社区 (community_skills + community_skill_versions)
```

### UUID 规则

| 实体 | UUID 来源 | 说明 |
|---|---|---|
| `community_skills.id` | **独立生成** | 社区项目唯一标识，不继承到任何地方 |
| `user_library_skills.id` | **独立生成** 或 **继承 `community_skill_versions.id`** | 本地创建时独立生成；从社区安装时继承社区版本 UUID（同一版本同一用户只能安装一次） |
| `community_skill_versions.id` | **继承 `user_library_skills.id`** | 发布时直接用仓库 skill 的 UUID 作为社区版本 ID |

### 数据继承规则

**共有字段（社区 ↔ 仓库双向继承）**：`name`, `display_name`, `description`, `tags`, `version`, `readme_md`

**仓库 → 社区发布时**：自动继承仓库的共有字段，`source` 字段仅在 fork 时填写

**社区 → 仓库安装时**：自动继承社区版本的共有字段 + `community_skill_id` 关联

**运行层 → 仓库收集时**：从 SKILL.md frontmatter 读取 `name`, `description`，其余手动填写或套用已有仓库 skill 模版（非即时性信息继承模版，版本号/changelog/时间戳即时填写）

---

## 文件系统架构

### 三层目录结构

```
# ═══ 社区层 (Community) ═══
# 全局共享，所有用户只读访问
archived_skill/
└── {community_skill_uuid}/              ← 一个社区项目
    ├── 1.0.0/                           ← 版本目录
    │   ├── README.md                    ← 该版本的总介绍文档
    │   └── skill/                       ← 实际 skill 内容
    │       ├── SKILL.md
    │       ├── references/
    │       ├── assets/
    │       └── ...
    ├── 1.1.0/
    │   ├── README.md
    │   └── skill/
    │       └── ...
    └── ...

# ═══ 仓库层 (Library) ═══
# 每个用户私有，每条 skill 一个目录（无版本子目录，每次上传是独立条目）
data/{user_uuid}/library/
└── {library_skill_id}/                  ← 一个仓库 skill 条目
    ├── README.md                        ← 该 skill 的总介绍文档
    └── skill/                           ← 实际 skill 内容
        ├── SKILL.md
        ├── references/
        └── ...

# ═══ 运行层 (Runtime) ═══
# 无版本概念，纯文件系统，无 DB 记录
data/{user_uuid}/skills/{name}/          ← 用户级 skill
data/{user_uuid}/{pid}/skills/{name}/    ← 项目级 skill
```

### 层间文件操作

| 操作 | 文件复制方向 | DB 写入 |
|---|---|---|
| **运行层 → 仓库** (收集) | `data/{user}/skills/{name}/` → `data/{user}/library/{lib_id}/skill/` | 写 `user_library_skills` |
| **仓库 → 社区** (发布) | `data/{user}/library/{lib_id}/skill/` → `archived_skill/{com_id}/{version}/skill/` | 写 `community_skill_versions`（首次还写 `community_skills`） |
| **社区 → 仓库** (安装) | `archived_skill/{com_id}/{version}/skill/` → `data/{user}/library/{lib_id}/skill/` | 写 `user_library_skills` |
| **仓库 → 运行层** (安装) | `data/{user}/library/{lib_id}/skill/` → `data/{user}/skills/{name}/` 或 `data/{user}/{pid}/skills/{name}/` | **无 DB 写入，纯文件复制** |
| **社区 → 运行层** (直接安装) | `archived_skill/{com_id}/{version}/skill/` → `data/{user}/skills/{name}/` 或 `data/{user}/{pid}/skills/{name}/` | 仅更新 `downloads` 计数 |

> **README.md 处理**：收集/发布时，`README.md` 存放在目录根下（与 `skill/` 同级），同时内容写入 DB 的 `readme_md` 字段，方便列表查询时直接展示。

---

## 一、 users 表迁移

现有 `users` 表增加 `role` 字段：

```sql
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';
```

| role 值 | 含义 |
|---|---|
| `user` | 普通用户 |
| `admin` | 社区全局管理员（审核所有社区发布） |

---

## 二、 社区模块 (Community)

### 1. community_skills (社区技能主表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 社区项目唯一 UUID（独立生成，不继承） |
| `owner_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 创建者（仅记录，权限判定用 `admin_uuids`） |
| `name` | TEXT | NOT NULL, UNIQUE | 技能唯一标识名 (kebab-case) |
| `display_name` | TEXT | - | 友好展示名称 |
| `description` | TEXT | NOT NULL | 一句话简短描述 |
| `admin_uuids` | TEXT | NOT NULL, DEFAULT '[]' | Skill 管理员列表（JSON 数组）。**创建时自动将 `owner_uuid` 加入**，权限检查只查此字段 |
| `likes` | INTEGER | NOT NULL, DEFAULT 0 | 点赞数（缓存计数，与 `community_skill_likes` 表同步） |
| `downloads` | INTEGER | NOT NULL, DEFAULT 0 | 全版本累计下载量 |
| `latest_version` | TEXT | DEFAULT NULL | 缓存最新 APPROVED 版本号，加速列表查询 |
| `created_at` | REAL | NOT NULL | 创建时间戳 |
| `updated_at` | REAL | NOT NULL | 最后更新时间戳 |

### 2. community_skill_versions (社区技能版本表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 版本 UUID（**继承自 `user_library_skills.id`**） |
| `skill_id` | TEXT | NOT NULL, FK → `community_skills(id)` ON DELETE CASCADE | 所属社区项目 |
| `version` | TEXT | NOT NULL | 版本号 (如 1.0.0) |
| `readme_md` | TEXT | DEFAULT '' | README 总介绍文档内容 |
| `changelog` | TEXT | DEFAULT '' | 版本更新说明 |
| `tags` | TEXT | NOT NULL, DEFAULT '[]' | 标签列表（JSON 数组）。社区列表展示取最新 APPROVED 版本的 tags |
| `archive_path` | TEXT | NOT NULL | 归档物理路径（如 `archived_skill/{com_skill_uuid}/{version}`） |
| `size_bytes` | INTEGER | NOT NULL | 版本文件包大小 |
| `downloads` | INTEGER | NOT NULL, DEFAULT 0 | 当前版本下载量 |
| `source` | TEXT | DEFAULT NULL | 来源说明（fork 时填写原 skill 信息） |
| `status` | TEXT | NOT NULL, DEFAULT 'PENDING_ADMIN' | 审核状态 |
| `submitted_by` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 提交者 |
| `created_at` | REAL | NOT NULL | 提交时间戳 |

**联合唯一约束**：`UNIQUE(skill_id, version)`

**status 枚举**：

| 状态 | 含义 |
|---|---|
| `PENDING_OWNER` | 等待 skill 管理员审核（贡献者提交时） |
| `REJECTED_OWNER` | 被 skill 管理员驳回 |
| `PENDING_ADMIN` | 等待社区全局管理员审核 |
| `APPROVED` | 审核通过，已上架 |
| `REJECTED_ADMIN` | 被全局管理员驳回 |

### 3. community_skill_likes (社区技能点赞表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `skill_id` | TEXT | NOT NULL, FK → `community_skills(id)` ON DELETE CASCADE | 社区项目 ID |
| `user_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 用户 UUID |
| `created_at` | REAL | NOT NULL | 点赞时间 |

**联合主键**：`PRIMARY KEY(skill_id, user_uuid)`

> 点赞/取消点赞时同步更新 `community_skills.likes` 计数字段。

### 4. community_skill_comments (社区技能评论表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 评论 UUID |
| `skill_id` | TEXT | NOT NULL, FK → `community_skills(id)` ON DELETE CASCADE | 社区项目 ID |
| `user_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 评论者 |
| `content` | TEXT | NOT NULL | 评论内容 (Markdown) |
| `parent_id` | TEXT | DEFAULT NULL, FK → `community_skill_comments(id)` ON DELETE CASCADE | 父评论 ID。NULL = 顶层评论，非 NULL = 楼中楼回复 |
| `depth` | INTEGER | NOT NULL, DEFAULT 0 | 嵌套深度。0 = 顶层评论，1 = 回复。**最大值 1，禁止更深嵌套** |
| `reply_to_uuid` | TEXT | DEFAULT NULL, FK → `users(uuid)` ON DELETE SET NULL | 被回复的用户 UUID。用于 depth=1 时显示「回复 @xxx」 |
| `likes` | INTEGER | NOT NULL, DEFAULT 0 | 点赞数（缓存计数，与 `community_comment_likes` 表同步） |
| `created_at` | REAL | NOT NULL | 创建时间 |
| `updated_at` | REAL | NOT NULL | 修改时间 |

> **嵌套规则**：最多 2 层。depth=0 的评论可被回复（生成 depth=1）。对 depth=1 的评论回复时，`parent_id` 仍指向其所属的 depth=0 评论（成为同级回复），`reply_to_uuid` 记录实际被回复的用户。

### 5. community_skill_contributors (社区技能贡献者表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `skill_id` | TEXT | NOT NULL, FK → `community_skills(id)` ON DELETE CASCADE | 社区项目 ID |
| `user_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 贡献者 |
| `role` | TEXT | NOT NULL, DEFAULT 'contributor' | 角色：`contributor` |
| `created_at` | REAL | NOT NULL | 加入时间 |

**联合主键**：`PRIMARY KEY(skill_id, user_uuid)`

> **权限层级**：`admin_uuids` 中的用户（含 owner）有管理和审核权限，`contributor` 仅有提交权限。权限检查只查 `community_skills.admin_uuids` 一个字段。

### 6. community_comment_likes (评论点赞表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `comment_id` | TEXT | NOT NULL, FK → `community_skill_comments(id)` ON DELETE CASCADE | 评论 ID |
| `user_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 用户 UUID |
| `created_at` | REAL | NOT NULL | 点赞时间 |

**联合主键**：`PRIMARY KEY(comment_id, user_uuid)`

> 点赞/取消点赞时同步更新 `community_skill_comments.likes` 计数字段。

### 7. community_comment_reports (评论举报表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 举报 UUID |
| `comment_id` | TEXT | NOT NULL, FK → `community_skill_comments(id)` ON DELETE CASCADE | 被举报的评论 ID |
| `reporter_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 举报人 |
| `reason` | TEXT | NOT NULL | 举报原因（如 `spam`, `harassment`, `inappropriate`, `other`） |
| `detail` | TEXT | DEFAULT '' | 举报详情说明 |
| `status` | TEXT | NOT NULL, DEFAULT 'PENDING' | 处理状态：`PENDING`, `RESOLVED`, `DISMISSED` |
| `resolved_by` | TEXT | DEFAULT NULL, FK → `users(uuid)` ON DELETE SET NULL | 处理人（全局 admin） |
| `resolved_at` | REAL | DEFAULT NULL | 处理时间 |
| `created_at` | REAL | NOT NULL | 举报时间 |

**联合唯一约束**：`UNIQUE(comment_id, reporter_uuid)`（同一用户对同一评论只能举报一次）

---

## 三、 仓库模块 (Library)

仓库不维护版本表。每次从运行层上传就是一个新的独立 skill 条目，避免冲突。版本号和 changelog 在上传时由用户填入。

### user_library_skills (仓库技能表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 仓库 skill UUID。本地创建时独立生成；从社区安装时**继承 `community_skill_versions.id`** |
| `user_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 拥有者 |
| `name` | TEXT | NOT NULL | 技能标识名 (kebab-case) |
| `display_name` | TEXT | DEFAULT NULL | 友好展示名 |
| `description` | TEXT | NOT NULL | 简短描述 |
| `readme_md` | TEXT | DEFAULT '' | README 总介绍文档 |
| `tags` | TEXT | NOT NULL, DEFAULT '[]' | 标签列表（JSON 数组），安装时从社区版本继承，收集时可套用模版 |
| `version` | TEXT | NOT NULL | 版本号（上传时填写） |
| `changelog` | TEXT | DEFAULT '' | 更新说明（上传时填写） |
| `source` | TEXT | DEFAULT NULL | 来源说明（fork 时填写） |
| `community_skill_id` | TEXT | DEFAULT NULL | 关联社区项目 ID（从社区安装时填写，本地创建为 NULL） |
| `local_path` | TEXT | NOT NULL | 本地物理存储路径（如 `data/{user_uuid}/library/{lib_skill_id}`） |
| `size_bytes` | INTEGER | NOT NULL, DEFAULT 0 | 文件大小 |
| `created_at` | REAL | NOT NULL | 创建/上传时间 |
| `updated_at` | REAL | NOT NULL | 最后更新时间 |

> **注意**：没有 `UNIQUE(user_uuid, name)` 约束——同一用户可以有多个同名 skill 条目（不同版本/不同次上传），每条都是独立实体。

---

## 四、 审核模块 (Review)

### skill_review_logs (审核日志表)

| 字段名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT | PRIMARY KEY | 日志 UUID |
| `version_id` | TEXT | NOT NULL, FK → `community_skill_versions(id)` ON DELETE CASCADE | 被审核的版本 |
| `reviewer_uuid` | TEXT | NOT NULL, FK → `users(uuid)` ON DELETE CASCADE | 审核人 |
| `action` | TEXT | NOT NULL | 操作：`approve`, `reject`, `submit`, `resubmit` |
| `from_status` | TEXT | NOT NULL | 审核前状态 |
| `to_status` | TEXT | NOT NULL | 审核后状态 |
| `note` | TEXT | DEFAULT '' | 审核备注 |
| `created_at` | REAL | NOT NULL | 操作时间 |

---

## 五、 审核流程

### 首次发布

```
仓库 skill → 收集面板填表 → 提交
  → community_skill_versions.status = PENDING_ADMIN
  → 社区全局管理员审核（users.role = 'admin'）
  → APPROVED (上架) 或 REJECTED_ADMIN (驳回)
```

### 贡献者更新

```
贡献者提交新版本
  → community_skill_versions.status = PENDING_OWNER
  → admin_uuids 中的管理员审核
  → PENDING_ADMIN
  → 社区全局管理员审核
  → APPROVED 或 REJECTED_ADMIN
```

### skill 管理员更新

```
admin_uuids 中的用户（含 owner）提交新版本
  → community_skill_versions.status = PENDING_ADMIN (跳过 owner 审核)
  → 社区全局管理员审核（users.role = 'admin'）
  → APPROVED 或 REJECTED_ADMIN
```

---

## 六、 收集面板数据流

### 运行层 → 仓库收集

```
1. 前端读取运行层 skill 目录的 SKILL.md
2. 解析 frontmatter → 提取 name, description
3. 预填模版匹配：
   a. 默认：用 frontmatter 的 name 匹配仓库中最新的同名 skill，自动继承其 tags, display_name, readme_md 等非即时性信息
   b. 可选：用户可手动选择仓库中任意 skill 作为模版（覆盖默认匹配）
4. 用户确认/修改预填的非即时性信息（name, display_name, description, tags, readme_md）
5. 用户填写即时性信息：version, changelog
6. 提交 → 后端：
   a. 生成新 user_library_skills 条目（新 UUID）
   b. 复制 data/{user}/skills/{name}/ → data/{user}/library/{lib_id}/skill/
   c. 将 readme_md 写入 data/{user}/library/{lib_id}/README.md
7. 每次上传都是一个新 skill 条目，互不冲突
```

### 仓库 → 社区发布收集

```
1. 后端返回仓库 skill 数据预填表单
2. 自动继承：name, display_name, description, tags, version, readme_md
3. 用户补充：changelog, source (仅 fork 时)
4. 提交 → 后端：
   a. 创建 community_skill_versions（首次还创建 community_skills）
   b. 复制 data/{user}/library/{lib_id}/skill/ → archived_skill/{com_id}/{version}/skill/
   c. 复制 README.md 到 archived_skill/{com_id}/{version}/README.md
5. community_skill_versions.id = user_library_skills.id（UUID 继承）
6. 进入审核流程
```

---

## 七、 索引

```sql
-- 社区
CREATE INDEX idx_community_skills_created_at ON community_skills(created_at);
CREATE INDEX idx_community_skills_downloads ON community_skills(downloads);
CREATE INDEX idx_community_skills_likes ON community_skills(likes);
CREATE INDEX idx_community_skills_owner ON community_skills(owner_uuid);
CREATE INDEX idx_community_skills_name ON community_skills(name);
CREATE INDEX idx_community_versions_skill ON community_skill_versions(skill_id);
CREATE INDEX idx_community_versions_status ON community_skill_versions(status);
CREATE INDEX idx_community_versions_submitted ON community_skill_versions(submitted_by);
CREATE INDEX idx_community_comments_skill ON community_skill_comments(skill_id);
CREATE INDEX idx_community_likes_skill ON community_skill_likes(skill_id);

-- 仓库
CREATE INDEX idx_library_skills_user ON user_library_skills(user_uuid);
CREATE INDEX idx_library_skills_community ON user_library_skills(community_skill_id);

-- 审核
CREATE INDEX idx_review_logs_version ON skill_review_logs(version_id);
CREATE INDEX idx_review_logs_reviewer ON skill_review_logs(reviewer_uuid);
```

---

## 八、 API 设计

### 社区 API (`/community`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/community/skills` | 列出社区技能（搜索、分页、排序、TAG 过滤） |
| GET | `/community/skills/{skill_id}` | 技能详情（含 README、贡献者列表） |
| GET | `/community/skills/{skill_id}/versions` | 列出版本（含版本信息、贡献者） |
| GET | `/community/skills/{skill_id}/versions/{version_id}` | 版本详情 |
| POST | `/community/skills/{skill_id}/install` | 安装到仓库（指定版本） |
| POST | `/community/skills/batch-install` | 批量安装到仓库 |
| POST | `/community/skills/{skill_id}/like` | 点赞/取消点赞（toggle，同步更新 `likes` 计数） |
| GET | `/community/skills/{skill_id}/comments` | 评论列表（分页，含楼中楼） |
| POST | `/community/skills/{skill_id}/comments` | 发表评论（depth=0 顶层，或 depth=1 回复） |
| PATCH | `/community/skills/{skill_id}/comments/{comment_id}` | 编辑评论（仅作者） |
| DELETE | `/community/skills/{skill_id}/comments/{comment_id}` | 删除评论（作者或管理员） |
| POST | `/community/skills/{skill_id}/comments/{comment_id}/like` | 评论点赞/取消（toggle） |
| POST | `/community/skills/{skill_id}/comments/{comment_id}/report` | 举报评论 |
| DELETE | `/community/skills/{skill_id}` | 删除社区技能（仅 `admin_uuids` 中的管理员或全局 admin） |

#### GET `/community/skills` 请求参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `keyword` | string | - | 搜索 name/display_name/description |
| `tags` | string (逗号分隔) | - | TAG 过滤（取最新版本的 tags 匹配） |
| `sort` | string | `popular` | 排序：`popular`, `newest`, `most_liked` |
| `limit` | int | 20 | 每页数量 |
| `offset` | int | 0 | 偏移量 |

#### GET `/community/skills` 响应

```json
{
  "skills": [
    {
      "id": "uuid",
      "owner_uuid": "uuid",
      "owner_username": "作者名",
      "name": "code-reviewer",
      "display_name": "代码审查助手",
      "description": "...",
      "downloads": 128,
      "likes": 42,
      "liked_by_me": true,
      "latest_version": "1.2.0",
      "tags": ["code", "review"],
      "source": null,
      "contributors": [
        {"user_uuid": "...", "username": "...", "role": "admin"},
        {"user_uuid": "...", "username": "...", "role": "contributor"}
      ],
      "created_at": 1717488000.0,
      "updated_at": 1717488000.0
    }
  ],
  "total": 150
}
```

> `tags` 和 `source` 取自最新 APPROVED 版本。`liked_by_me` 通过当前用户 UUID 查 `community_skill_likes` 表。

#### GET `/community/skills/{skill_id}` 响应

```json
{
  "id": "uuid",
  "owner_uuid": "uuid",
  "owner_username": "作者名",
  "name": "code-reviewer",
  "display_name": "代码审查助手",
  "description": "...",
  "readme_md": "# Code Reviewer\n\n...",
  "downloads": 128,
  "likes": 42,
  "liked_by_me": false,
  "latest_version": "1.2.0",
  "tags": ["code", "review"],
  "source": null,
  "contributors": [
    {"user_uuid": "...", "username": "...", "role": "admin"},
    {"user_uuid": "...", "username": "...", "role": "contributor"}
  ],
  "versions": [
    {
      "id": "uuid",
      "version": "1.2.0",
      "changelog": "...",
      "tags": ["code", "review"],
      "downloads": 50,
      "status": "APPROVED",
      "submitted_by": "uuid",
      "created_at": 1717488000.0
    }
  ],
  "created_at": 1717488000.0,
  "updated_at": 1717488000.0
}
```

#### POST `/community/skills/{skill_id}/install` 请求

```json
{
  "version_id": "uuid (可选，默认最新 APPROVED 版本)",
  "target": "library | project | user",
  "pid": "项目 ID (target=project 时必填)"
}
```

> `target=library`：安装到仓库（DB 记录 + 文件复制）；`target=project|user`：直接安装到运行层（仅文件复制 + 更新下载计数）。

#### POST `/community/skills/batch-install` 请求

```json
{
  "installs": [
    {"skill_id": "uuid", "version_id": "uuid (可选)"}
  ],
  "target": "library | project | user",
  "pid": "项目 ID (target=project 时必填)"
}
```

---

### 仓库 API (`/library`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/library/skills` | 列出我的仓库技能 |
| GET | `/library/skills/{skill_id}` | 仓库技能详情 |
| POST | `/library/skills/collect` | 从运行层收集 skill 到仓库（收集面板提交，每次生成新条目） |
| DELETE | `/library/skills/{skill_id}` | 删除仓库 skill |
| POST | `/library/skills/{skill_id}/publish` | 发布到社区（收集面板提交，进入审核） |
| POST | `/library/skills/{skill_id}/install` | 安装到项目/用户运行层（纯文件复制） |
| POST | `/library/skills/batch-install` | 批量安装到项目/用户 |

#### POST `/library/skills/collect` 请求

```json
{
  "source_path": "skills/code-reviewer (运行层 skill 相对路径)",
  "source_scope": "user | project",
  "source_pid": "项目 ID (scope=project 时必填)",
  "template_skill_id": "uuid (可选，套用已有仓库 skill 作为模版，继承非即时性信息)",
  "name": "code-reviewer",
  "display_name": "代码审查助手",
  "description": "...",
  "readme_md": "...",
  "tags": ["code", "review"],
  "version": "1.0.0",
  "changelog": "初始版本"
}
```

> 每次 collect 都生成一个全新的 `user_library_skills` 条目（新 UUID），不会与已有条目冲突。`template_skill_id` 为空时，后端自动按 `name` 匹配仓库中最新同名 skill 作为模版；用户也可显式指定仓库中任意 skill 的 UUID 作为模版。

#### POST `/library/skills/{skill_id}/publish` 请求

```json
{
  "changelog": "...",
  "source": null,
  "community_skill_id": "uuid (可选，已有社区项目则追加版本；新发布则后端自动创建)"
}
```

> 发布时 `community_skill_versions.id` = `user_library_skills.id`。version、tags、readme_md 等从仓库 skill 继承，不需重填。

#### GET `/library/skills` 响应

```json
{
  "skills": [
    {
      "id": "uuid",
      "name": "code-reviewer",
      "display_name": "代码审查助手",
      "description": "...",
      "readme_md": "...",
      "tags": ["code", "review"],
      "version": "1.0.0",
      "source": null,
      "community_skill_id": null,
      "created_at": 1717488000.0,
      "updated_at": 1717488000.0
    }
  ]
}
```

#### POST `/library/skills/{skill_id}/install` 请求

```json
{
  "target": "project | user",
  "pid": "项目 ID (target=project 时必填)"
}
```

---

### 收集面板 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/library/skills/parse-runtime` | 解析运行层 SKILL.md + 自动匹配仓库同名模版，返回预填数据 |
| GET | `/library/skills/{skill_id}/template` | 获取指定仓库 skill 数据作为模版（用户手动选择时调用） |
| GET | `/library/skills/{skill_id}/publish-form` | 获取发布到社区的预填数据 |

#### GET `/library/skills/parse-runtime` 请求参数

| 参数 | 说明 |
|---|---|
| `scope` | `user` 或 `project` |
| `pid` | 项目 ID (scope=project 时) |
| `skill_name` | 运行层 skill 目录名 |

#### 响应

```json
{
  "from_frontmatter": {
    "name": "code-reviewer",
    "display_name": null,
    "description": "一句话描述（从 frontmatter 读取）",
    "readme_md": "SKILL.md 全文"
  },
  "matched_template": {
    "skill_id": "uuid (匹配到的仓库同名 skill ID，未匹配则 null)",
    "name": "code-reviewer",
    "display_name": "代码审查助手",
    "description": "...",
    "tags": ["code", "review"],
    "readme_md": "...",
    "version": "1.0.0"
  },
  "suggested_version": "1.1.0"
}
```

> `matched_template` 是按 frontmatter 的 `name` 匹配仓库中最新的同名 skill。若未匹配则为 `null`，前端仅用 `from_frontmatter` 的数据预填。`suggested_version` 基于匹配到的版本自动递增（如 1.0.0 → 1.1.0），未匹配则默认 `1.0.0`。

---

### 审核 API

#### 全局管理员面板 (`/admin`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/reviews` | 列出待审核版本（status=PENDING_ADMIN，分页） |
| GET | `/admin/reviews/{version_id}` | 审核详情（含 skill 信息、归档内容预览） |
| POST | `/admin/reviews/{version_id}/approve` | 批准 |
| POST | `/admin/reviews/{version_id}/reject` | 驳回（需附 note） |

#### Skill 管理员面板 (`/owner`)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/owner/reviews` | 列出待我审核的版本（status=PENDING_OWNER，我在该 skill 的 `admin_uuids` 中） |
| GET | `/owner/reviews/{version_id}` | 审核详情 |
| POST | `/owner/reviews/{version_id}/approve` | 批准（→ PENDING_ADMIN） |
| POST | `/owner/reviews/{version_id}/reject` | 驳回（→ REJECTED_OWNER） |

#### 贡献者 & 管理员管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/community/skills/{skill_id}/contributors` | 列出贡献者 |
| POST | `/community/skills/{skill_id}/contributors` | 添加贡献者（仅 `admin_uuids` 中的管理员） |
| DELETE | `/community/skills/{skill_id}/contributors/{user_uuid}` | 移除贡献者（仅 `admin_uuids` 中的管理员） |
| PATCH | `/community/skills/{skill_id}/admins` | 更新 `admin_uuids`（仅 owner，即创建者） |

---

## 九、 完整建表 SQL

```sql
-- ═══════════════════ 社区模块 ═══════════════════

CREATE TABLE IF NOT EXISTS community_skills (
    id TEXT PRIMARY KEY,
    owner_uuid TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    description TEXT NOT NULL,
    admin_uuids TEXT NOT NULL DEFAULT '[]',
    likes INTEGER NOT NULL DEFAULT 0,
    downloads INTEGER NOT NULL DEFAULT 0,
    latest_version TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (owner_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_skill_versions (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    readme_md TEXT DEFAULT '',
    changelog TEXT DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    archive_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    downloads INTEGER NOT NULL DEFAULT 0,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_ADMIN',
    submitted_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(skill_id, version),
    FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
    FOREIGN KEY (submitted_by) REFERENCES users(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_skill_likes (
    skill_id TEXT NOT NULL,
    user_uuid TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (skill_id, user_uuid),
    FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
    FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_skill_comments (
    id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    user_uuid TEXT NOT NULL,
    content TEXT NOT NULL,
    parent_id TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    reply_to_uuid TEXT,
    likes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
    FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
    FOREIGN KEY (reply_to_uuid) REFERENCES users(uuid) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS community_comment_likes (
    comment_id TEXT NOT NULL,
    user_uuid TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (comment_id, user_uuid),
    FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
    FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_comment_reports (
    id TEXT PRIMARY KEY,
    comment_id TEXT NOT NULL,
    reporter_uuid TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    resolved_by TEXT,
    resolved_at REAL,
    created_at REAL NOT NULL,
    UNIQUE(comment_id, reporter_uuid),
    FOREIGN KEY (comment_id) REFERENCES community_skill_comments(id) ON DELETE CASCADE,
    FOREIGN KEY (reporter_uuid) REFERENCES users(uuid) ON DELETE CASCADE,
    FOREIGN KEY (resolved_by) REFERENCES users(uuid) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS community_skill_contributors (
    skill_id TEXT NOT NULL,
    user_uuid TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'contributor',
    created_at REAL NOT NULL,
    PRIMARY KEY (skill_id, user_uuid),
    FOREIGN KEY (skill_id) REFERENCES community_skills(id) ON DELETE CASCADE,
    FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

-- ═══════════════════ 仓库模块 ═══════════════════

CREATE TABLE IF NOT EXISTS user_library_skills (
    id TEXT PRIMARY KEY,
    user_uuid TEXT NOT NULL,
    name TEXT NOT NULL,
    display_name TEXT,
    description TEXT NOT NULL,
    readme_md TEXT DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL,
    changelog TEXT DEFAULT '',
    source TEXT,
    community_skill_id TEXT,
    local_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (user_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

-- ═══════════════════ 审核模块 ═══════════════════

CREATE TABLE IF NOT EXISTS skill_review_logs (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL,
    reviewer_uuid TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at REAL NOT NULL,
    FOREIGN KEY (version_id) REFERENCES community_skill_versions(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_uuid) REFERENCES users(uuid) ON DELETE CASCADE
);

-- ═══════════════════ 索引 ═══════════════════

CREATE INDEX IF NOT EXISTS idx_community_skills_created_at ON community_skills(created_at);
CREATE INDEX IF NOT EXISTS idx_community_skills_downloads ON community_skills(downloads);
CREATE INDEX IF NOT EXISTS idx_community_skills_likes ON community_skills(likes);
CREATE INDEX IF NOT EXISTS idx_community_skills_owner ON community_skills(owner_uuid);
CREATE INDEX IF NOT EXISTS idx_community_skills_name ON community_skills(name);
CREATE INDEX IF NOT EXISTS idx_community_versions_skill ON community_skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_community_versions_status ON community_skill_versions(status);
CREATE INDEX IF NOT EXISTS idx_community_versions_submitted ON community_skill_versions(submitted_by);
CREATE INDEX IF NOT EXISTS idx_community_comments_skill ON community_skill_comments(skill_id);
CREATE INDEX IF NOT EXISTS idx_community_comments_parent ON community_skill_comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_community_likes_skill ON community_skill_likes(skill_id);
CREATE INDEX IF NOT EXISTS idx_comment_likes_comment ON community_comment_likes(comment_id);
CREATE INDEX IF NOT EXISTS idx_comment_reports_comment ON community_comment_reports(comment_id);
CREATE INDEX IF NOT EXISTS idx_comment_reports_status ON community_comment_reports(status);
CREATE INDEX IF NOT EXISTS idx_library_skills_user ON user_library_skills(user_uuid);
CREATE INDEX IF NOT EXISTS idx_library_skills_community ON user_library_skills(community_skill_id);
CREATE INDEX IF NOT EXISTS idx_review_logs_version ON skill_review_logs(version_id);
CREATE INDEX IF NOT EXISTS idx_review_logs_reviewer ON skill_review_logs(reviewer_uuid);
```

---

## 十、 与现有表的迁移关系

| 现有表/字段 | 迁移方向 |
|---|---|
| `community_skills` (旧扁平表) | **删除重建**为新的 `community_skills` + `community_skill_versions`，旧数据需迁移脚本 |
| `community_skills.archive_path` | 移入 `community_skill_versions.archive_path` |
| `community_skills.size_bytes` | 移入 `community_skill_versions.size_bytes` |
| `community_skills.license` | 废弃（改为 TAG 或 README 中说明） |
| `community_skills.compatibility` | 废弃（同上） |
| `users.role` | **新增字段**，默认 `'user'` |

> **注意**：旧 `community_skills` 表没有版本概念，迁移时每条旧记录生成一条 `community_skill_versions`（version = '1.0.0', status = 'APPROVED'），同时将旧的 `owner_uuid` 写入新 `community_skills.admin_uuids` 数组中。

---

## 十一、 表总览

| 模块 | 表名 | 状态 |
|---|---|---|
| 用户 | `users` + role 字段 | **迁移** |
| 社区 | `community_skills` | **重建** |
| 社区 | `community_skill_versions` | **新增** |
| 社区 | `community_skill_likes` | **新增** |
| 社区 | `community_skill_comments` | **新增** |
| 社区 | `community_comment_likes` | **新增** |
| 社区 | `community_comment_reports` | **新增** |
| 社区 | `community_skill_contributors` | **新增** |
| 仓库 | `user_library_skills` | **新增** |
| 审核 | `skill_review_logs` | **新增** |
| **总计** | **9 张新表 + 1 迁移** | |
