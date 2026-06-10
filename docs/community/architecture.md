# Community 架构梳理

## 三层架构与数据流转

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         社区层 (Community)                                          │
│                                                                                                     │
│  ┌─────────────────────┐        ┌─────────────────────┐        ┌─────────────────────┐              │
│  │  community_skills   │        │community_skill_     │        │  community_skill_   │              │
│  │  (技能主表)         │◄───────┤  versions           │        │    comments         │              │
│  │                     │   1:N  │  (版本表)           │        │    (评论表)         │              │
│  │  id ────────────────│───┐    │                     │        │                     │              │
│  │  owner_uuid         │   │    │  id = library_id ◄──│───┐    │  skill_id ──────────│──┐           │
│  │  name               │   │    │  skill_id ──────────│───│────│  user_uuid          │  │           │
│  │  display_name       │   │    │  version (用户填)   │   │    │  content            │  │           │
│  │  description        │   │    │  readme_md (继承)   │   │    │  parent_id          │  │           │
│  │  admin_uuids        │   │    │  changelog (用户填) │   │    │  depth              │  │           │
│  │  likes              │   │    │  tags (继承)        │   │    │  likes              │  │           │
│  │  downloads          │   │    │  archive_path       │   │    └─────────────────────┘  │           │
│  │  latest_version     │   │    │  size_bytes         │   │                             │           │
│  └─────────────────────┘   │    │  status             │   │    ┌─────────────────────┐  │           │
│                            │    │  submitted_by       │   │    │  community_skill_   │  │           │
│  ┌─────────────────────┐   │    └─────────────────────┘   │    │    likes            │  │           │
│  │  community_skill_   │   │                              │    │  (技能点赞)         │  │           │
│  │    admins           │   │    ┌─────────────────────┐   │    │  skill_id ──────────│──┘           │
│  │  (技能管理员)       │   │    │  skill_review_logs  │   │    │  user_uuid          │              │
│  │  skill_id ──────────│───┘    │  (审核日志)         │   │    └─────────────────────┘              │
│  │  user_uuid          │        │  version_id ────────│───┘                                         │
│  └─────────────────────┘        │  action             │        ┌─────────────────────┐              │
│                                 │  from_status        │        │  community_comment_ │              │
│  ┌─────────────────────┐        │  to_status          │        │    reports          │              │
│  │  community_skill_   │        │  note               │        │  (评论举报)         │              │
│  │    contributors     │        └─────────────────────┘        └─────────────────────┘              │
│  │  (贡献者)           │                                                                            │
│  └─────────────────────┘                                                                            │
│                                                                                                     │
│  文件: archived_skill/{skill_id}/{version}/skill/                                                   │
│  只有 status=APPROVED 的版本才显示在社区列表                                                        │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                    ▲
                      ┌─────────────────────────────┼─────────────────────────────┐
                      │                             │                             │
                      │ ① Publish (仓库→社区)      │ ④ Install to Library       │ 
                      │   文件: 复制到 archived_skill │   (社区→仓库)             │
                      │  DB: 新建 version 记录      │   文件: 复制到 library/     │
                      │ 首次: +新建 community_skill │   DB: 新建 library 记录     │
                      │                             │   继承: name/desc/tags/     │
                      │                             │          version/changelog  │
                      │                             │          readme_md/size     │
                      ▼                             │                             │
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         仓库层 (Library)                                            │
│                                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              user_library_skills                                            │    │
│  │                                                                                             │    │
│  │  id (= version_id 或新 UUID) ──────────┐                                                   │    │
│  │  user_uuid                              │                                                   │    │
│  │  name ◄────── 继承自 SKILL.md           │                                                   │    │
│  │  display_name ◄── 继承自 SKILL.md       │                                                   │    │
│  │  description ◄─── 继承自 SKILL.md       │    发布时复用                                     │    │
│  │  readme_md ◄────── SKILL.md body        │──────────────────▶ community_skill_versions.id    │    │
│  │  tags ◄────────── 继承 (收集时="[]")    │    library_id = version_id                        │    │
│  │  version ◄──────── 继承 (收集时="1.0.0")│                                                   │    │
│  │  changelog ◄───── 继承 (收集时固定值)   │                                                   │    │
│  │  community_skill_id ────────────────────│──── 有值=来自社区，空=来自运行层                   │    │
│  │  local_path                             │                                                   │    │
│  │  size_bytes                             │                                                   │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                                     │
│  文件结构: data/{user_uuid}/library/{library_id}/                                                   │
│    ├── skill/           (技能文件夹，包含 SKILL.md, references/, assets/)                           │
│    └── README.md        (从 SKILL.md body 提取，独立存储便于快速读取)                               │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
      ▲                                         │
      │                                         │
      │ ② Collect (运行层→仓库)                │ ③ Install from Library (仓库→运行层)
      │   文件: 复制到 library/                 │   文件: 复制到 skills/
      │   DB: 新建 library 记录                 │   DB: 无写入
      │   继承: name/desc from SKILL.md         │   继承: name 作为目录名
      │   固定: version="1.0.0"                 │
      │          changelog="Initial collect"    │
      │          tags="[]"                      │
      │          source="runtime"               │
      │          community_skill_id=NULL        │
      ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         运行层 (Runtime)                                            │
│                                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │  用户级: data/{user_uuid}/skills/{skill_name}/                                              │    │
│  │  项目级: data/{user_uuid}/{pid}/skills/{skill_name}/                                        │    │
│  │  全局级: data/skills/{skill_name}/ (只读)                                                   │    │
│  └─────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                                     │
│  入口: SKILL.md (frontmatter: name, display_name, description, license, compatibility)              │
│  子目录: references/, assets/                                                                       │
│  无 DB 记录，纯文件系统                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 流转编号说明

| 编号 | 流转 | 文件操作 | DB 操作 | 继承规则 |
|---|---|---|---|---|
| ① | **Publish** (仓库→社区) | 复制到 `archived_skill/{id}/{ver}/` | 新建 `community_skill_versions`；首次发布额外新建 `community_skills` + `community_skill_admins` | name/desc/tags/readme_md 继承自仓库；version/changelog 用户填写 |
| ② | **Collect** (运行层→仓库) | 复制到 `library/{id}/skill/` + 创建 `README.md` | 新建 `user_library_skills`，`source="runtime"` | name 从 SKILL.md 读取；其他元数据从模板继承（最佳匹配或用户选择）；readme_md 从模板继承或从零生成；version="1.0.0" 固定；community_skill_id=null |
| ③ | **Install from Library** (仓库→运行层) | 复制到 `skills/{name}/` | **无写入** | 全部继承，name 作为目录名 |
| ④ | **Install to Library** (社区→仓库) | 复制到 `library/{version_id}/skill/` | 新建 `user_library_skills`，`source="community"` | 全部继承自社区版本；`community_skill_id` 建立关联；复用 `version_id` 作为 `library_id` |
| ⑤ | **Install** (社区→运行层) | 复制到 `skills/{name}/` | 更新 `downloads` 计数 | 全部继承，name 作为目录名 |
| ⑥ | **Fork** (仓库→仓库) | 复制到 `library/{new_id}/skill/` | 新建 `user_library_skills`，`source="fork"` | 元数据默认继承源记录，可通过请求体覆盖；version 继承（不重置）；保留 `community_skill_id` 关联 |

### UUID 复用规则

```
library_id (仓库 UUID)
    │
    ├──▶ user_library_skills.id           (仓库表主键)
    │
    └──▶ community_skill_versions.id      (发布时复用为版本 ID)

community_skill_id (社区技能 UUID)
    │
    ├──▶ community_skills.id              (社区主表主键)
    │
    ├──▶ community_skill_versions.skill_id (版本表外键)
    │
    ├──▶ community_skill_admins.skill_id   (管理员表外键)
    │
    └──▶ user_library_skills.community_skill_id (仓库反向关联)
```

### 存储分工

| 内容 | DB | 文件 | 说明 |
|---|---|---|---|
| name, description, tags, version | ✅ | ✅ (SKILL.md frontmatter) | DB 用于查询排序，文件用于 AI 调用 |
| readme_md | ✅ (从 SKILL.md body 提取) | ✅ (README.md，与 skill/ 同级) | DB 快速展示，文件保留原始 |
| SKILL.md body (正文) | ❌ | ✅ (skill/SKILL.md) | 正文只存文件 |
| references/, assets/ | ❌ | ✅ (skill/references/, skill/assets/) | 资源只存文件 |
| size_bytes, downloads, likes | ✅ | ❌ | 统计数据只存 DB |
| 审核状态/日志/点赞/评论/举报 | ✅ | ❌ | 纯 DB 交互 |
| 来源 (运行层/社区) | ✅ (community_skill_id 有值/空) | ❌ | 通过 community_skill_id 推断 |

### 仓库文件结构

```
data/{user_uuid}/library/{library_id}/
├── skill/                    # 技能文件夹
│   ├── SKILL.md              # 技能入口文件 (frontmatter + body)
│   ├── references/           # 参考资料 (可选)
│   └── assets/               # 资源文件 (可选)
└── README.md                 # 从 SKILL.md body 提取，独立存储
```

- `library_id` 在收集时生成新 UUID，在社区安装时复用 `version_id`
- `README.md` 与 `skill/` 同级，便于快速读取展示

---

## 核心表单与数据传递

### 1. 运行层 → 仓库 (Collect)

**触发**: 用户在 SkillManagerDialog 中点击「收集到仓库」

**请求**: `POST /library/skills/collect`

```json
{
  "skill_name": "my-skill",      // 运行层中的技能文件夹名
  "template_id": null            // 可选：指定模板技能 ID，为空则自动匹配最佳模板
}
```

**模板匹配逻辑**:
1. 根据 `skill_name` 在仓库中查找同名技能 → 作为**最佳匹配**建议
2. 用户可手动选择仓库中其他技能作为模板
3. 无合适模板时，元数据从零开始（name 从 SKILL.md 读取，其余为空）

**数据流**:

```
┌──────────────────┐     ┌───────────────────────────────────────────┐
│  运行层文件系统  │     │              模板匹配                     │
│                  │     │                                           │
│ skills/          │     │  1. 根据 skill_name 查找仓库同名技能      │
│   my-skill/      │────▶│     → 找到：作为最佳匹配建议              │
│     SKILL.md     │     │     → 未找到：用户手动选择或从零开始      │
│     references/  │     │                                           │
│     assets/      │     │  2. template_id 指定时直接使用该模板      │
└──────────────────┘     └───────────────────┬───────────────────────┘
                                             │
                                             ▼
                           ┌──────────────────────────────────────────┐
                           │              仓库层 DB                   │
                           │                                          │
                           │  user_library_skills 记录:               │
                           │    id = 新 UUID                          │
                           │    name = SKILL.md frontmatter.name      │
                           │    元数据 = 从模板继承（如有）           │
                           │    readme_md = 从模板继承或从零生成      │
                           │    community_skill_id = NULL             │
                           └──────────────────────────────────────────┘

                           ┌──────────────────┐
                           │   仓库层文件系统 │
                           │                  │
                           │ library/         │
                           │   {library_id}/  │
                           │     skill/       │◀─── 从运行层复制
                           │       SKILL.md   │
                           │       references/│
                           │       assets/    │
                           │     README.md    │◀─── 从模板继承或从零生成
                           └──────────────────┘
```

**响应**: `user_library_skills` 记录

```json
{
  "id": "uuid-xxx",
  "user_uuid": "user-uuid",
  "name": "my-skill",
  "display_name": "从模板继承或为空",
  "description": "从模板继承或从 SKILL.md 读取",
  "readme_md": "从模板继承或从零生成",
  "tags": "从模板继承或为 []",
  "version": "1.0.0",
  "changelog": "Initial collect",
  "community_skill_id": null,
  "local_path": "data/{user_uuid}/library/{library_id}",
  "size_bytes": 12345,
  "created_at": 1717800000.0,
  "updated_at": 1717800000.0
}
```

**来源推断**: `community_skill_id` 有值表示来自社区，为空表示来自运行层收集。

**模板匹配 API**: `GET /library/skills/match-template?skill_name=xxx`
- 返回最佳匹配的仓库技能（同名）
- 前端可用于预填表单或让用户选择模板

---

### 2. 仓库 → 社区 (Publish)

**触发**: 用户在仓库面板中点击「发布到社区」，填写版本号和变更说明

**前置操作 - Fork（从社区安装的技能修改后发布）**:
- 如果技能是从社区安装的（`community_skill_id` 有值），用户修改后需要先 fork
- Fork 创建新的 `library_id`，继承原有元数据作为模板
- 用户可在表单中修改元数据后再发布

**请求**: `POST /library/skills/{library_id}/publish`

```json
{
  "version": "1.1.0",         // 语义化版本号 x.y.z
  "changelog": "新增xxx功能"   // 本次变更说明
}
```

**发布表单预填逻辑**:
- `name`, `display_name`, `description`, `tags`, `readme_md` 从仓库记录继承（作为默认值）
- `version` 基于最新已审核版本号末位+1（建议值）
- `changelog` 用户必须填写

**数据流 (首次发布)**:

```
┌──────────────────┐     ┌──────────────────────────────────────────────────┐
│  仓库层记录      │     │                    社区层 DB                     │
│                  │     │                                                  │
│ library_skills:  │     │  ① 创建 community_skills 记录:                  │
│   name ──────────│────▶│     id = 新 UUID                                 │
│   display_name   │     │     owner_uuid = 当前用户                        │
│   description    │     │     name = library.name                          │
│   community_     │     │     admin_uuids = [当前用户]                     │
│     skill_id=NULL│     │                                                  │
│                  │     │  ② 创建 community_skill_versions 记录:          │
└──────────────────┘     │     id = library_id (复用!)                      │
                         │     skill_id = 新社区技能 UUID                   │
                         │     version = "1.1.0"                            │
                         │     status = "PENDING_OWNER"                     │
                         │     archive_path = "archived_skill/{id}/{ver}"   │
                         │                                                  │
                         │  ③ 反向更新仓库记录:                            │
                         │     community_skill_id = 社区技能 UUID           │
                         │                                                  │
                         │  ④ 同步管理员子表:                              │
                         │     community_skill_admins:                      │
                         │       skill_id, user_uuid = 当前用户             │
                         └──────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐
│  仓库层文件      │     │  社区归档文件    │
│                  │     │                  │
│ library/         │     │ archived_skill/  │
│   {lib_id}/      │────▶│   {skill_id}/    │
│     skill/       │     │     {version}/   │
│       SKILL.md   │     │       skill/     │
│       ...        │     │         SKILL.md │
└──────────────────┘     │         ...      │
                         └──────────────────┘
```

**数据流 (更新已有关联技能)**:

```
直接继承version的skill_id作为仓库中的skill_id以此作为区分
```

**审核状态流转**:

```
PENDING_OWNER ──(Owner 审核通过)──▶ PENDING_ADMIN ──(Admin 审核通过)──▶ APPROVED
      │                                      │
      └──────(Owner 审核拒绝)──▶ REJECTED ◄──┴──────(Admin 审核拒绝)──┘
```

---

### 3. 社区 → 运行层/仓库 (Install)

**触发**: 用户在社区面板中点击「安装到我的技能」或「安装到项目」或「安装到仓库」

**请求**: `POST /community/skills/{skill_id}/install`

```json
{
  "target": "user",           // "user" | "project" | "library"
  "pid": null,                // target="project" 时必填
  "version_id": "version-uuid" // 要安装的版本 ID
}
```

**数据流**:

```
┌──────────────────┐     ┌──────────────────────────────────────────┐
│  社区归档文件    │     │              目标位置                    │
│                  │     │                                          │
│ archived_skill/  │     │  target="user":                          │
│   {skill_id}/    │     │    → data/{user_uuid}/skills/{name}/     │
│     {version}/   │────▶│                                          │
│       skill/     │     │  target="project":                       │
│         SKILL.md │     │    → data/{user_uuid}/{pid}/skills/{name}│
│         ...      │     │                                          │
└──────────────────┘     │  target="library":                       │
                         │    → data/{user_uuid}/library/{version_id}/│
                         │      skill/                              │
                         │    + 创建 user_library_skills 记录       │
                         │    + version_id 复用为 library_id        │
                         └──────────────────────────────────────────┘

安装后更新计数:
  community_skills.downloads += 1
  community_skill_versions.downloads += 1
```

**安装到仓库时的去重逻辑**:
- 复用 `version_id` 作为 `library_id`
- 如果 `version_id` 已存在于当前用户仓库（发布者发布时已创建），返回 409 错误
- readme_md 从社区版本记录获取

**安装到仓库时创建的记录**:

```json
{
  "id": "version-uuid",
  "user_uuid": "当前用户",
  "name": "skill-name",
  "display_name": "...",
  "description": "...",
  "readme_md": "从社区版本记录获取",
  "tags": "[\"tag1\",\"tag2\"]",
  "version": "1.1.0",
  "changelog": "...",
  "community_skill_id": "来源社区技能UUID",
  "local_path": "data/{user_uuid}/library/{version_id}",
  "size_bytes": 12345
}
```

---

### 4. Fork（仓库→仓库，用于修改后重新发布）

**触发**: 用户修改从社区安装的技能后，想要发布新版本

**请求**: `POST /library/skills/{library_id}/fork`

**数据流**:

```
┌──────────────────┐     ┌──────────────────────────────────────────┐
│  原仓库记录      │     │              新仓库记录                  │
│                  │     │                                          │
│ library_skills:  │     │  id = 新 UUID                           │
│   name ──────────│────▶│  name = 继承                            │
│   display_name   │     │  display_name = 继承（可修改）          │
│   description    │     │  description = 继承（可修改）           │
│   readme_md      │     │  readme_md = 继承（可修改）             │
│   tags           │     │  tags = 继承（可修改）                  │
│   community_     │     │  community_skill_id = 继承              │
│     skill_id     │     │  version = "1.0.0"                      │
└──────────────────┘     └──────────────────────────────────────────┘

文件复制:
  library/{old_id}/skill/ → library/{new_id}/skill/
```

**用途**:
1. 修改从社区安装的技能
2. 保留原有元数据作为模板
3. 发布到社区时，元数据作为表单默认值

---

### 5. 仓库 → 运行层 (Install from Library)

### 4. 仓库 → 运行层 (Install from Library)

**触发**: 用户在仓库面板中点击「安装到运行层」

**请求**: `POST /library/skills/{library_id}/install`

```json
{
  "target": "user",    // "user" | "project"
  "pid": null          // target="project" 时必填
}
```

**数据流**: 纯文件复制，无 DB 写入

```
data/{user_uuid}/library/{library_id}/skill/
    │
    ▼
data/{user_uuid}/skills/{name}/       (target=user)
    或
data/{user_uuid}/{pid}/skills/{name}/ (target=project)
```

---

### 5. 发布表单预填 (Publish Form)

**触发**: 用户打开发布对话框时自动加载

**请求**: `GET /library/skills/{library_id}/publish-form`

**响应**:

```json
{
  "library_skill": {
    "id": "library-uuid",
    "name": "my-skill",
    "display_name": "我的技能",
    "description": "...",
    "readme_md": "从 SKILL.md body 提取",
    "tags": "[]",
    "version": "1.0.0",
    "changelog": "Initial collect",
    "community_skill_id": null,
    "local_path": "data/{user_uuid}/library/{library_id}",
    "size_bytes": 12345
  },
  "community_skill": null,          // 已关联的社区技能 (首次发布为 null)
  "latest_approved_version": null,  // 最新已审核版本
  "suggested_version": "1.0.0"      // 建议版本号 (末位+1)
}
```

**版本号建议逻辑**:
- 无历史版本 → `"1.0.0"`
- 有历史版本 `"1.2.3"` → `"1.2.4"` (末位+1)

---

### 6. 社区技能详情 (Community Detail)

**请求**: `GET /community/skills/{skill_id}`

**响应**:

```json
{
  "id": "community-skill-uuid",
  "owner_uuid": "owner-uuid",
  "name": "my-skill",
  "display_name": "我的技能",
  "description": "技能描述",
  "likes": 42,
  "downloads": 128,
  "created_at": 1717800000.0,
  "updated_at": 1717850000.0,
  "version": "1.1.0",
  "tags": "[\"ai\",\"productivity\"]",
  "size_bytes": 12345,
  "liked_by_me": true,
  "contributors": [
    {
      "skill_id": "skill-uuid",
      "user_uuid": "contributor-uuid",
      "role": "contributor",
      "created_at": 1717800000.0
    }
  ],
  "latest_version": {
    "id": "version-uuid",
    "skill_id": "skill-uuid",
    "version": "1.1.0",
    "readme_md": "# My Skill\n\n...",
    "changelog": "新增功能",
    "tags": "[\"ai\"]",
    "archive_path": "archived_skill/{skill_id}/1.1.0",
    "size_bytes": 12345,
    "downloads": 64,
    "status": "APPROVED",
    "submitted_by": "user-uuid",
    "created_at": 1717850000.0
  }
}
```

---

### 7. 评论创建 (Comment Create)

**请求**: `POST /community/skills/{skill_id}/comments`

```json
{
  "content": "这个技能很棒！",      // 1-1000 字符
  "parent_id": null,               // 父评论 ID (NULL=顶级评论)
  "reply_to_uuid": null            // 被回复者 UUID (仅二级回复时有值)
}
```

**评论嵌套规则**:
- `parent_id=null` → 顶级评论 (depth=0)
- `parent_id=xxx` + 父评论 depth=0 → 二级回复 (depth=1)
- `parent_id=xxx` + 父评论 depth>=1 → **拒绝** (最大嵌套2层)

**响应**: 评论记录

```json
{
  "id": "comment-uuid",
  "skill_id": "skill-uuid",
  "user_uuid": "commenter-uuid",
  "content": "这个技能很棒！",
  "parent_id": null,
  "depth": 0,
  "reply_to_uuid": null,
  "likes": 0,
  "created_at": 1717800000.0,
  "updated_at": 1717800000.0
}
```

---

### 8. 审核流程 (Review Flow)

#### Owner 审核 (技能管理员)

**请求**: `POST /owner/reviews/{version_id}/approve` 或 `/reject`

```json
{
  "note": "审核通过，代码质量良好"   // 审核备注 (可选)
}
```

**数据流**:
1. 验证版本存在且 status=`PENDING_OWNER`
2. 验证当前用户是该技能的管理员 (community_skill_admins 表)
3. 写入 skill_review_logs 记录
4. 更新 community_skill_versions.status

**状态流转**:
- approve: `PENDING_OWNER` → `PENDING_ADMIN`
- reject: `PENDING_OWNER` → `REJECTED`

#### Admin 审核 (系统管理员)

**请求**: `POST /admin/reviews/{version_id}/approve` 或 `/reject`

```json
{
  "note": "已确认无安全问题"
}
```

**数据流**:
1. 验证用户 role=`admin`
2. 验证版本存在且 status=`PENDING_ADMIN`
3. 写入 skill_review_logs 记录
4. 更新 community_skill_versions.status
5. **approve 时额外**: 更新 community_skills.latest_version = 此版本号

---

### 9. 点赞与举报

**技能点赞**: `POST /community/skills/{skill_id}/like`
- Toggle 模式: 未点赞→点赞, 已点赞→取消
- 响应: `{"liked": true/false}`

**评论点赞**: `POST /community/comments/{comment_id}/like`
- 同上 Toggle 模式

**评论举报**: `POST /community/comments/{comment_id}/report`

```json
{
  "reason": "垃圾广告",        // 1-100 字符
  "detail": "发布无关链接..."   // 详细说明 (可选)
}
```

---

## 审核状态完整流转图

```
                    ┌─────────────────────────────────────────────────┐
                    │                仓库层 (Library)                  │
                    │                                                 │
                    │  user.library.publish_from_library()             │
                    │    │                                            │
                    │    ▼                                            │
                    │  创建 community_skill_versions 记录              │
                    │  status = "PENDING_OWNER"                       │
                    └────────────────────┬────────────────────────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                              社区审核流程                                       │
│                                                                                │
│   PENDING_OWNER ◄─────────────────────────────────────────────────────────┐    │
│        │                                                                  │    │
│        │  Owner (技能管理员) 审核                                           │    │
│        │  POST /owner/reviews/{version_id}/approve                        │    │
│        │  POST /owner/reviews/{version_id}/reject                         │    │
│        │                                                                  │    │
│        ├──── approve ────▶ PENDING_ADMIN ◄────────────────────────────┐   │    │
│        │                       │                                      │   │    │
│        │                       │  Admin (系统管理员) 审核               │   │    │
│        │                       │  POST /admin/reviews/{version_id}/   │   │    │
│        │                       │    approve / reject                  │   │    │
│        │                       │                                      │   │    │
│        │                       ├──── approve ────▶ APPROVED (上架)    │   │    │
│        │                       │                                      │   │    │
│        │                       └──── reject ────▶ REJECTED           │   │    │
│        │                                                                  │    │
│        └──── reject ─────▶ REJECTED                                      │    │
│                                                                                │
│  审核日志记录在 skill_review_logs 表:                                           │
│    action: APPROVE_BY_OWNER / REJECT_BY_OWNER / APPROVE_BY_ADMIN / REJECT_BY_ADMIN│
│    from_status → to_status                                                    │
│    note: 审核备注                                                              │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 数据库表关系图

```
users (uuid)
  │
  ├──▶ projects (pid)
  │      └──▶ sessions (sid)
  │             └──▶ messages (msg_id)
  │
  ├──▶ community_skills (id) [owner_uuid]
  │      │
  │      ├──▶ community_skill_versions (id) [skill_id, submitted_by]
  │      │      │
  │      │      └──▶ skill_review_logs (id) [version_id, reviewer_uuid]
  │      │
  │      ├──▶ community_skill_likes (skill_id, user_uuid)
  │      │
  │      ├──▶ community_skill_comments (id) [skill_id, user_uuid, parent_id]
  │      │      │
  │      │      ├──▶ community_comment_likes (comment_id, user_uuid)
  │      │      │
  │      │      └──▶ community_comment_reports (id) [comment_id, reporter_uuid, resolved_by]
  │      │
  │      ├──▶ community_skill_contributors (skill_id, user_uuid)
  │      │
  │      └──▶ community_skill_admins (skill_id, user_uuid)
  │
  ├──▶ user_library_skills (id) [user_uuid, community_skill_id]
  │
  └──▶ user_model_configs (config_id) [user_uuid]
```

---

## 前端界面与 API 对应

| 界面 | 组件 | 调用的 API | 触发时机 |
|---|---|---|---|
| 社区列表 | `CommunityView.vue` | `GET /community/skills` | 页面加载/搜索/翻页 |
| 技能详情 | `CommunityView.vue` 弹层 | `GET /community/skills/{id}` | 点击技能卡片 |
| 安装到用户 | 详情弹层按钮 | `POST /community/skills/{id}/install` | 点击「安装到我的技能」 |
| 安装到项目 | 详情弹层按钮 | `POST /community/skills/{id}/install` | 选择项目后点击安装 |
| 安装到仓库 | 详情弹层按钮 | `POST /community/skills/{id}/install` | 点击「安装到仓库」 |
| ZIP上传 | 上传弹层 | `POST /community/skills/upload` | 选择/拖拽 ZIP 文件 |
| 点赞 | 详情弹层按钮 | `POST /community/skills/{id}/like` | 点击爱心图标 |
| 评论列表 | 详情弹层评论区 | `GET /community/skills/{id}/comments` | 展开评论区 |
| 发表评论 | 评论输入框 | `POST /community/skills/{id}/comments` | 提交评论 |
| 回复评论 | 回复输入框 | `POST /community/skills/{id}/comments` | 提交回复 |
| 删除评论 | 评论操作菜单 | `DELETE /community/skills/{id}/comments/{cid}` | 确认删除 |
| 评论点赞 | 评论操作按钮 | `POST /community/comments/{cid}/like` | 点击赞 |
| 评论举报 | 评论操作按钮 | `POST /community/comments/{cid}/report` | 填写举报原因 |
| 仓库列表 | `LibraryView.vue` | `GET /library/skills` | 打开仓库页面 / 筛选排序 |
| 仓库详情 | `LibraryView.vue` 弹层 | `GET /library/skills/{id}` | 点击仓库卡片 |
| 安装到运行层 | 详情弹层按钮 | `POST /library/skills/{id}/install` | 点击安装按钮 |
| Fork 技能 | 详情弹层按钮 | `POST /library/skills/{id}/fork` | 点击 Fork 按钮 |
| ZIP 上传 | `LibraryUploadDialog.vue` | `POST /library/skills/upload` | 点击「上传 ZIP」按钮 |
| 模板匹配 | 收集面板 | `GET /library/skills/match-template?skill_name=xxx` | 收集前自动匹配 |
| 收集技能 | `CollectPanel.vue` (待建) | `POST /library/skills/collect` | 确认收集 |
| 发布表单 | `PublishPanel.vue` (待建) | `GET /library/skills/{id}/publish-form` | 打开发布面板 |
| 发布提交 | `PublishPanel.vue` | `POST /library/skills/{id}/publish` | 填写版本号后提交 |
| Owner审核 | `OwnerReviewPanel.vue` (待建) | `GET /owner/reviews` | 打开Owner审核面板 |
| Owner审核操作 | 审核面板按钮 | `POST /owner/reviews/{id}/approve\|reject` | 审核决策 |
| Admin审核 | `AdminReviewPanel.vue` (待建) | `GET /admin/reviews` | 打开Admin审核面板 |
| Admin审核操作 | 审核面板按钮 | `POST /admin/reviews/{id}/approve\|reject` | 审核决策 |
| 排行榜 | `LeaderboardPanel.vue` (待建) | `GET /community/leaderboard` | 点击排行榜入口 |
| 用户搜索 | 贡献者添加弹层 | `GET /users/search?q=xxx` | 搜索用户 |
| 贡献者管理 | 详情弹层设置 | `GET/POST/DELETE /community/skills/{id}/contributors` | 管理贡献者 |
| 举报列表 | `AdminReportPanel.vue` (待建) | `GET /admin/community/reports` | 管理员查看举报 |

---

## 现有实现完整度评估

### ✅ 已就位

| 层级 | 组件 | 状态 |
|---|---|---|
| 数据库 | community_skills 表 | ✅ |
| 数据库 | community_skill_versions 表 | ✅ |
| 数据库 | community_skill_likes 表 | ✅ |
| 数据库 | community_skill_comments 表 | ✅ |
| 数据库 | community_comment_likes 表 | ✅ |
| 数据库 | community_comment_reports 表 | ✅ |
| 数据库 | community_skill_contributors 表 | ✅ |
| 数据库 | community_skill_admins 表 | ✅ |
| 数据库 | user_library_skills 表 | ✅ |
| 数据库 | skill_review_logs 表 | ✅ |
| 后端 | 社区列表/详情 API | ✅ |
| 后端 | 社区排行榜 API | ✅ |
| 后端 | 社区安装 API (含三种目标) | ✅ |
| 后端 | 社区点赞/评论/举报 API | ✅ |
| 后端 | 贡献者管理 API (列表/添加/删除) | ✅ |
| 后端 | 仓库收集/发布/安装 API | ✅ |
| 后端 | 仓库模板匹配 API | ✅ |
| 后端 | 仓库文件编辑 API (列表/读取/写入) | ✅ |
| 后端 | 用户名搜索 API | ✅ |
| 后端 | Owner 审核 API | ✅ |
| 后端 | Admin 审核 API | ✅ |
| 后端 | Admin 举报列表 API | ✅ |
| 后端 | 审核日志 API | ✅ |
| 前端 | 社区列表页面 | ✅ |
| 前端 | 技能详情弹层 | ✅ |
| 前端 | 安装到用户/项目 | ✅ |
| 前端 | ZIP 上传 | ✅ |
| 前端 | 点赞/评论/举报 UI | ✅ |

### ✅ 已就位 (前端 — 仓库模块)

| 组件 | 说明 |
|---|---|
| 仓库面板 | `LibraryView.vue` — 卡片网格列表 + 筛选/排序/分页 + 详情弹层（安装/Fork） |
| ZIP 上传弹窗 | `LibraryUploadDialog.vue` — 批量拖拽上传 + 进度条 + 队列管理 |

### ❌ 缺失 (前端)

| 组件 | 说明 |
|---|---|
| 收集面板 | 运行层→仓库的收集表单 |
| 发布面板 | 仓库→社区的发布表单 (版本号/changelog) |
| Owner 审核面板 | 技能管理员审核界面 |
| Admin 审核面板 | 全局管理员审核界面 |
| 排行榜面板 | 热门/最新技能排行 |
| 贡献者管理 UI | 添加/移除贡献者的界面 |
| 举报管理 UI | 管理员查看/处理举报的界面 |
