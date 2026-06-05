# 社区 & 仓库系统 重构执行计划

本文档基于 `docs/community/dbdesign.md` 设计方案，梳理了后端的实施执行步骤，确保系统可以有条不紊地完成重构并迁移老数据。

---

## 阶段一：数据库架构演进与数据迁移 (Database Migration)

> 目标：建立新的表结构，并安全地迁移现有的旧 `community_skills` 数据。

**1. 修改初始化代码 (`backend/db.py` -> `setup_database`)**
*   **users表**：添加 `ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user';`。
*   **创建新表**：按照设计文档中的 SQL，创建以下 8 张新表并建立所有指定的索引：
    *   社区相关：`community_skill_versions`, `community_skill_likes`, `community_skill_comments`, `community_comment_likes`, `community_comment_reports`, `community_skill_contributors`
    *   仓库相关：`user_library_skills`
    *   审核相关：`skill_review_logs`
*   **重建旧表**：由于旧版 `community_skills` 结构大改（去除了 `archive_path`, `size_bytes` 等，增加了 `admin_uuids` 等），需要执行平滑迁移：
    1.  创建临时新表 `community_skills_new`。
    2.  读取旧表数据，将每条记录写入 `community_skills_new`（`admin_uuids` 填入 `owner_uuid` 的 JSON 数组，初始化 `likes=0`）。
    3.  为每条旧记录在 `community_skill_versions` 插入一条对应的记录（`version='1.0.0'`, `status='APPROVED'`，复制旧的 `archive_path` 和 `size_bytes`）。
    4.  删除旧表，将新表重命名为 `community_skills`。
    5.  建立索引。

## 阶段二：底层数据访问层重构 (Data Access Facade)

> 目标：更新 `DatabaseFacade` 中的子 Facade，封装所有的 SQL 读写逻辑，屏蔽底层 SQL 细节。

**1. 社区服务层 (`CommunitySkillsFacade`)**
*   更新 `create` / `get_by_id` 等基础方法以适应新表结构（不再写入 `archive_path`，需连表查最新版本）。
*   新增 `likes` 相关的原子操作（点赞 toggle 事务：写记录 + 更新计数）。
*   新增评论相关 CRUD 方法（含楼中楼验证逻辑：最多 2 层）。
*   新增举报相关方法。
*   新增贡献者及 `admin_uuids` 管理方法。

**2. 新增仓库服务层 (`UserLibrarySkillsFacade`)**
*   实现基础 CRUD，支撑后续收集面板逻辑。
*   提供按 `user_uuid` 和 `name` 匹配最新记录的方法（用于表单自动预填）。

**3. 新增审核服务层 (`ReviewLogsFacade`)**
*   提供写入审核日志的方法。
*   提供查询某版本历史审核记录的方法。

## 阶段三：文件系统逻辑改造 (File System & Path Logic)

> 目标：适配三层架构中不同的物理目录结构和复制逻辑。

**1. 修改路径解析逻辑 (`backend/community.py` / `file.py`)**
*   **社区目录**：`archived_skill/{skill_id}/{version}/`（增加 version 嵌套）。
*   **仓库目录**：`data/{user_uuid}/library/{library_id}/`（没有 version 嵌套，每次生成新的 UUID）。
*   **收集操作 (Collect)**：从 `skills/{name}` 复制到 `library/{library_id}/skill/`，并将 `README.md` 提取到 `library/{library_id}/README.md`。
*   **发布操作 (Publish)**：从 `library/{library_id}/skill/` 复制到 `archived_skill/{skill_id}/{version}/skill/`，并同步 `README.md`。

## 阶段四：收集面板 API 与仓库 API 开发 (`/library`)

> 目标：实现本地数据进入仓库，再从仓库通往社区的第一步。

**1. 收集面板 API**
*   实现 `GET /library/skills/parse-runtime`：读取本地 `SKILL.md`，调用 Facade 查找是否存在同名最新 skill 记录，返回 `from_frontmatter` 和 `matched_template`。
*   实现 `GET /library/skills/{skill_id}/template`：提供明确选择模版的接口。
*   实现 `GET /library/skills/{skill_id}/publish-form`。

**2. 仓库核心 API**
*   实现 `POST /library/skills/collect`：生成新记录，执行文件复制（步骤三）。
*   实现 `GET /library/skills` 及 `GET /library/skills/{skill_id}`。
*   实现 `POST /library/skills/{skill_id}/publish`：处理 UUID 继承逻辑 (`version_id = library_id`)，执行文件复制并插入 `community_skill_versions`（状态置为 PENDING_ADMIN 或 PENDING_OWNER）。
*   实现 `POST /library/skills/{skill_id}/install` (仓库到运行层的安装逻辑：纯文件复制)。

## 阶段五：社区 API 升级 (`/community`)

> 目标：重构公开展示与互动相关的 API。

**1. 列表与详情接口升级**
*   `GET /community/skills`：支持 `tags` 的 JSON 检索（SQLite JSON 函数），按最新 APPROVED 版本的标签过滤。
*   `GET /community/skills/{skill_id}`：聚合并返回主表信息、最新版本信息、贡献者列表，以及当前用户的 `liked_by_me` 状态。
*   `GET /community/skills/{skill_id}/versions`：返回已上架的历史版本。

**2. 安装逻辑升级**
*   `POST /community/skills/{skill_id}/install`：根据 payload 下载指定版本。支持下载到 library（带 DB 记录）或直接到项目/用户级（不带 DB 记录）。

**3. 互动模块 (Likes / Comments / Reports)**
*   实现评论的 CRUD (`/comments`)。
*   实现针对主技能和评论的双重点赞 API (`/like` 及 `/comments/{id}/like`)。
*   实现举报 API (`/comments/{id}/report`)。

## 阶段六：审核流与权限管理开发 (`/admin`, `/owner`)

> 目标：实现完整的设计权限流与两级审核体系。

**1. 贡献者提交流**
*   贡献者（无 admin 权限）发布时，版本状态进入 `PENDING_OWNER`。

**2. Owner (Skill 管理员) 审核**
*   实现 `GET /owner/reviews`：列出当前用户在 `admin_uuids` 中、且状态为 `PENDING_OWNER` 的版本。
*   实现 `POST /owner/reviews/{version_id}/approve` (流转到 `PENDING_ADMIN`) 及 `reject`。

**3. 全局 Admin 审核**
*   实现 `GET /admin/reviews`：需校验当前登录用户 `role == 'admin'`。
*   实现 `POST /admin/reviews/{version_id}/approve` (上架，流转为 `APPROVED`，更新缓存 `latest_version`) 及 `reject`。

## 阶段七：功能验证

暂不完成功能验证。
而是完成接口的开发。
