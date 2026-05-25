# Teachi Frontend

基于 Vue 3 + Vite + Tailwind 的 AI 聊天前端，对接 FastAPI 后端，支持账号鉴权、科目与会话管理、SSE 流式对话、Markdown/LaTeX/Mermaid 渲染、用户级 / 项目级技能（Skill）的管理和按需挂载，以及社区技能的 ZIP 上传发布、安装与删除。

## 目录结构

```
frontend/
├─ index.html              Vite 入口 HTML，仅挂载 <div id="app">
├─ package.json            依赖与脚本（vite / vue / vue-router / tailwind / katex / mermaid / markdown-it 等）
├─ vite.config.ts          开发代理：把 /auth /loop /users /projects /sessions /messages /tools /community /health 转发到后端
├─ tsconfig.json
├─ postcss.config.js       Tailwind v4 PostCSS 插件配置
└─ src/
   ├─ main.ts              createApp(App).use(router).mount('#app')
   ├─ style.css            全局样式：Tailwind + KaTeX + highlight.js 主题 + 自定义 .markdown-body 作用域
   ├─ vite-env.d.ts        Vite 环境类型声明
   ├─ App.vue              应用外壳：登录条件渲染 + 侧边栏 + header + <RouterView> + AIConfigDialog
   ├─ api.ts               后端 HTTP 客户端：鉴权、资源 CRUD、SSE、文件 API、模型配置 API
   ├─ config/              前端固定参数（API/技能/聊天/社区/UI 时间等）集中配置
   ├─ skills.ts            Skill 领域逻辑：frontmatter 校验、结构化读写、SKILL.md 模板
   ├─ router/
   │  └─ index.ts          路由表 + afterEach 设 document.title（静态 title）
   ├─ composables/
   │  ├─ useAuth.ts        token / bootstrapping / preparing / 登录 / 登出 / onTokenReady 钩子
   │  ├─ useProjects.ts    模块级 projects 单例 + load/upsert/remove/prepend/reset，loadProjects 去重并发
   │  ├─ useProjectSkills.ts 每个 pid 的技能列表缓存 + refresh，跨 App.vue / ChatView 共享
   │  └─ useLayout.ts      sidebarOpen / isMobile / handleResize / closeSidebarOnMobile
   ├─ views/
   │  ├─ OverviewView.vue  `/`：科目卡片总览 + 新建科目
   │  ├─ SubjectView.vue   `/projects/:pid`：该科目会话列表 + 首条消息创建会话
   │  ├─ ChatView.vue      `/projects/:pid/sessions/:sid`：消息流 + composer + SSE 主循环 + skill picker
   │  └─ CommunityView.vue `/community`：社区技能列表、ZIP 上传、详情、安装与作者删除
   ├─ components/
   │  ├─ MessageContent.vue       Markdown 消息渲染与代码块复制、Mermaid 延迟渲染
   │  ├─ RenameInline.vue         行内重命名输入（回车提交 / Esc 取消）
   │  ├─ RowMenu.vue              列表项右上三点菜单（重命名 / 删除）
   │  ├─ ConfirmDialog.vue        二次确认对话框（危险操作，含删除回合）
   │  ├─ EditPromptDialog.vue     编辑后重放：textarea + Ctrl/⌘+Enter 提交 / Esc 取消
   │  ├─ SkillChips.vue           已选技能的 chip 行（发送时随消息带走）
   │  ├─ SkillPicker.vue          @ 触发的技能下拉选择器，支持搜索与键盘导航
   │  ├─ SkillManagerDialog.vue   用户级 / 项目级技能管理对话框（结构化表单 + 原始兜底）
   │  └─ AIConfigDialog.vue       用户模型配置管理对话框（CRUD、连通性测试、激活控制）
   └─ markdown/
      ├─ renderer.ts       markdown-it 单例 + KaTeX + 代码块 / 链接 / mermaid 自定义渲染 + DOMPurify
      ├─ highlight.ts      highlight.js 按需注册语言
      └─ mermaid.ts        mermaid 懒加载与 DOM 内占位替换
```

## 模块依赖关系

```
main.ts
 └─ App.vue (外壳)
    ├─ components/AIConfigDialog.vue ── 用户模型配置管理（连通性测试 + 激活状态）
    ├─ composables/useAuth         ── token / bootstrapping / preparing / onTokenReady
     ├─ composables/useProjects     ── projects 列表单例（跨视图共享）
     ├─ composables/useLayout       ── sidebarOpen / isMobile
     ├─ router/index.ts             ── 路由表 + document.title 默认值
     ├─ api.ts                      所有后端调用的统一出口
    ├─ config/                     固定参数集中出口（api/skills/chat/community 等）
     ├─ skills.ts                   ── 依赖 api.ts 的通用文件 API
     └─ <RouterView>
         ├─ views/OverviewView.vue  ── useProjects / useLayout + Row/Rename/Confirm
         ├─ views/SubjectView.vue   ── useProjects / useLayout + listSessions/createSession/...
         ├─ views/ChatView.vue      ── useAuth(preparing) + useProjects + listSessions
                                        + sendChatMessage/stopChatGeneration + SkillPicker/Chips
         └─ views/CommunityView.vue ── 社区 skill 列表 / ZIP 上传 / 详情 / 安装 / 作者删除
```

- `api.ts` 是所有后端通信的唯一出口，封装 `fetch` + 401 自动刷新、JWT 本地存储、SSE 帧解析、通用文件 API
- `skills.ts` 把 Skill 视为「`skills/<name>/` 文件夹，入口为 `SKILL.md`」，业务层全部走 `api.ts` 的通用文件 API
- `markdown/` 三个文件是纯渲染层，不依赖后端
- 不引入 Pinia：跨视图共享状态走 composable 单例（模块级 `ref`），视图独占状态（messages/draft/streaming 等）在各自视图的 `<script setup>` 里
- 登录态是条件渲染，不进路由：`App.vue` 顶层 `v-if="bootstrapping || !isAuthenticated"` 先渲染登录卡片，`v-else` 里才挂 `<RouterView>`，因此未登录访问任何 URL 都会看到登录表单，登录后原 URL 继续生效

## 路由

| 路径 | View | meta.title | 状态边界 |
|---|---|---|---|
| `/` | `OverviewView` | `科目总览` | 科目列表共享（`useProjects`） |
| `/projects/:pid` | `SubjectView` | 动态（科目名） | 该项目会话列表；视图独占 |
| `/projects/:pid/sessions/:sid` | `ChatView` | 动态（科目 / 会话） | 消息 / 草稿 / SSE 全部随视图卸载释放 |
| `/community` | `CommunityView` | `社区` | 社区技能列表、ZIP 上传、详情、安装；视图独占 |
| `/:pathMatch(.*)*` | — | — | 404 重定向到 `/` |

- `ChatView` 用 `:key="${pid}:${sid}"` 强制按会话重建，避免切换 sid 时状态串联
- SubjectView 创建首条消息时跳转到 `/projects/:pid/sessions/:sid?initial=<text>`，ChatView 挂载后消费 `initial`、调 `router.replace` 去掉 query 再发送
- `document.title` 由 `router.afterEach`（静态）+ SubjectView / ChatView 的 watcher（动态）合力设置
- `App.vue` 的面包屑和 header 按钮按 `$route.name` 分支显示；项目技能按钮在 `route.params.pid` 存在时显示（subject 与 chat 两个视图都可用）
- 侧边栏标题区有「社区」入口，跳转到 `/community`

## 已完成的功能

### 1. 认证

- 登录 / 注册双模式切换（`/auth/login`、`/auth/register`），邮箱记忆到 `localStorage`
- Access token 存 `localStorage`，refresh token 由后端 HttpOnly Cookie 承载
- 启动时若本地有 token 直接进入；无 token 或已失效则尝试 `/auth/refresh`
- 401 自动刷新：`api.ts` 里任意请求命中 401 会静默调用 `/auth/refresh` 重试一次
- 登出清空所有本地状态并请求 `/auth/logout`

### 2. 科目与会话（路由三态）

三条路由驱动三个视图（详见上文「路由」一节）：

| 路径 / View | 说明 |
|---|---|
| `/` → `OverviewView` | 科目总览：卡片列表 + 底部「输入科目名直接新建」。每张卡片支持右上三点菜单改名 / 删除 |
| `/projects/:pid` → `SubjectView` | 该科目下的历史会话列表 + 底部「输入首条消息 → 自动新建会话并跳到 chat 发送」。每条会话支持改名 / 删除 |
| `/projects/:pid/sessions/:sid` → `ChatView` | 具体会话的消息流 + 输入框 + 流式生成 |

- 侧边栏显示最近 10 个科目，点击即 `router.push({ name: 'subject', params: { pid } })`，底部「查看全部科目」跳回 `/`
- 顶栏面包屑按 `$route.name` 分支：`科目总览` / `科目 / <名>` / `<科目> / <会话>`
- 侧边栏项目按钮的 active 态由 `$route.params.pid === project.pid` 判断
- 响应式：宽度 < 768px 切换到移动端布局，侧边栏变浮层 + 遮罩，`useLayout().closeSidebarOnMobile()` 在跳转前自动关闭
- 归属校验降级：URL 手改到不存在或不属于当前用户的 pid/sid，SubjectView / ChatView 的 `onMounted` 会 `router.replace` 到上一层（chat → subject → overview）
- 浏览器前进 / 后退、F5 刷新、URL 分享三件事由路由天然支持

### 3. 聊天主循环（SSE）

- `POST /loop/{sid}`，`action=send` / `regenerate` / `stop`，请求头必带 `Authorization` + `X-Nonce` + `X-Nonce-Timestamp`
- 用 `fetch` + `ReadableStream` 读 SSE，自己按 `\n\n` 分帧，比 `EventSource` 多了携带 body 和自定义头的能力
- 处理的帧类型：
  - `text_delta` —— 拼接到当前 assistant 消息的 content 并触发自动滚动
  - `tool_call` —— 在输入框上方显示「正在调用 XX」
  - `tool_result` —— 清除工具状态
  - `done` —— 携带 `msg_id`（成功）、`anchor_msg_id`（本回合 anchor）或 `error` / `error_code`（失败）
- 发送后立即乐观 push 一条 `pending: true` 的 assistant 占位气泡，收到 `done` 后再 `loadMessages()` 拉服务端权威版本
- 「停止生成」：调用 `POST /loop/{sid}` 带 `action=stop`，同时 `AbortController.abort()` 关闭前端 SSE。停止后把刚发出去那条 user 文本回填到输入框（仅当输入框为空时），便于用户改一改再发
- 自动贴底滚动：监听容器 scroll，只有用户停留在底部（阈值 32px）时才自动贴底

### 4. Composer 交互

- 输入框高度随内容自适应（44px ~ 240px）
- `Ctrl/⌘ + Enter` 发送，`Enter` 换行
- `@` 触发 `SkillPicker`：从光标向前匹配 `@xxx` 就展开抽屉
- `SkillPicker` 支持搜索（name + description）与上下 / Enter / Esc 键盘导航
- 选中技能后在输入框上方显示 chip，可 × 移除；发送时自动拼前缀 `[本轮请优先考虑使用技能：xxx、yyy]\n\n<原始内容>`

### 5. 技能管理（Skill）

Skill 在后端是 `skills/<name>/` 文件夹约定，核心入口为 `SKILL.md`，可含 `references/`、`assets/` 等子目录。前端完全通过通用文件 API 读写。

`SkillManagerDialog` 支持：

- 左栏列表 + 「新建技能」按钮
- 中栏文件树：点击技能后打开整个 `skills/<name>/` 文件夹，默认选中 `SKILL.md`
  - 固定展示入口文件 `SKILL.md`
  - 默认展示虚拟 `references/`、`assets/` 文件夹，只有创建目录或在其中创建文件时才落盘
  - 文件树面板和文件夹行提供新建文件 / 新建文件夹按钮；文件夹只允许 `references` / `assets`
  - 新建文件只允许 `.md`、`.txt`、`.json`、`.yaml`、`.yml`，暂不支持嵌套目录
- 右栏编辑器：
  - `SKILL.md` 使用结构化表单
  - `name`（受限 `^[\u4e00-\u9fa5a-zA-Z0-9]+(-[\u4e00-\u9fa5a-zA-Z0-9]+)*$`，支持中文、大小写字母、数字和连字符，长度 ≤ 64，不含保留词 `anthropic` / `claude`）
  - `description`（≤ 1024）
  - `license`、`compatibility`（≤ 500）作为高级字段折叠
  - `body` 仅提示字符 / 行数，不做硬限制
- 其它 `.md` 用普通 Markdown 文本编辑器，仅在存在 frontmatter 时检查 YAML 语法
- `.json` / `.yaml` / `.yml` 保存前做语法解析，`.txt` 不做格式校验
- 旧文件 frontmatter 无法结构化解析时自动降级为「原始编辑」模式，保存前仍做 frontmatter 合法性兜底校验
- `yaml.stringify` 生成 frontmatter，避免人工漏空格之类 YAML 陷阱
- 用户级技能在已保存且无未保存修改时可「发布到社区」，调用 `POST /community/skills` 并传 `skill_name`，后端复制整个 `skills/<name>/` 文件夹到 `archived_skill/{id}/`，再解析其中 `SKILL.md` 的 frontmatter 生成社区元信息
- 社区页也支持直接上传 Skill ZIP 发布，调用 `POST /community/skills/upload`，前端只接受 `.zip`，并在发送前拦截超过 40MB 的单个文件

「我的技能」（用户级）和「项目技能」（项目级）共用同一对话框，靠 `FileSpace` 判别：

```ts
type FileSpace =
  | { kind: 'user'; userId: string }
  | { kind: 'project'; pid: string }
```

对应后端路径 `/users/{user_id}/files` 或 `/projects/{pid}/files`。

### 6. 社区技能广场

`/community` 由 `CommunityView.vue` 提供，入口在侧边栏标题区的「社区」按钮。

- 列表调用 `GET /community/skills`，支持按 `keyword` 搜索技能名 / 描述，分页大小固定 20
- 排序支持 `popular`（下载数降序）和 `newest`（发布时间降序）
- 顶部「上传 ZIP」按钮打开本地文件选择器，调用 `uploadCommunitySkillZip(file)` 上传原始 zip body 到 `POST /community/skills/upload`
- 上传前前端检查文件名后缀必须是 `.zip`，单个 zip 文件大小必须 ≤ 40MB；后端继续校验 zip 格式、目录结构、`SKILL.md` frontmatter、路径安全和解压后总大小；zip 内 `reference/` 与 `references/` 都接受并统一归档为 `references/`；发布名称只看 `SKILL.md` 的 `frontmatter.name`，不看 zip 文件名或顶层文件夹名
- 点击卡片后调用 `GET /community/skills/{id}` 打开详情弹层，展示描述、大小、发布时间、license 和 compatibility
- 「安装到我的技能」调用 `POST /community/skills/{id}/install`，成功后把归档目录复制到用户级 `skills/<name>/` 并刷新下载数
- 「安装到项目」调用同一接口并传 `{ target: "project", pid }`，成功后把归档目录复制到项目级 `skills/<name>/`
- 作者本人在详情弹层中可删除发布，调用 `DELETE /community/skills/{id}`
- 从已有用户级技能发布仍在「我的技能」管理对话框里：选中已保存且未修改的用户级技能后显示「发布到社区」

### 7. Markdown / 代码 / 数学 / Mermaid 渲染

`MessageContent.vue` + `markdown/renderer.ts` 流水线：

1. `markdown-it` 单例：`html: false` + `linkify: true`，链接强制 `target="_blank"` + `rel=noopener noreferrer nofollow`
2. `markdown-it-texmath` + KaTeX：支持 `$...$` / `$$...$$` / `\(...\)` / `\[...\]`
3. 自定义 `fence` 规则：
   - `mermaid` 语言 → 输出 `<pre data-lang="mermaid" data-source="...">` 占位，流式结束后由 `mermaid.ts` 懒加载替换为 SVG
   - 其它语言 → `highlight.js` 着色，包一层 `.code-block` 头 + 「复制」按钮
4. DOMPurify 兜底：打开 html / svg / mathMl 白名单，放行 KaTeX 的 `eq / eqn / section` 和自定义的 `data-*` 属性
5. 消息容器里挂 click 代理，把 `[data-copy]` 按钮接上复制 → 「已复制」1.5s 反馈

Mermaid 渲染失败降级为可见的 error 卡片而不是白屏。

### 8. 消息历史

- `GET /sessions/{sid}/messages` 拉原始 PydanticAI `ModelMessage` 序列化数据
- 前端只渲染 `version === 0` 的条目（活跃版本，历史版本通过版本切换按钮访问）
- `MessageItem.anchor_msg_id` 是回合 anchor，同一回合内 `user` / `tool_call` / `tool_result` / `assistant` 共享，`DisplayMessage` 也会带上方便后续重放 / 切换 / 删除使用
- 解析逻辑在 `api.ts#parseMessage`：
  - `kind === 'user'` + `parsed.kind === 'request'` → 取 `user-prompt` 部分
  - `kind === 'assistant' | 'agent_response'` + `parsed.kind === 'response'` → 取 `text` 部分
  - 工具调用 / 返回类消息在前端不展示

### 9. 其它

- 消息复制：鼠标悬停 assistant 气泡左下显示复制按钮，带 1.5s 视觉反馈
- 错误体 → 文案：`api.ts#getErrorMessage` 兼容 `ApiError` / `Error` / `{ detail: ... }` / `{ detail: { message } }`

### 10. 重放 / 编辑 PROMPT / 版本切换 / 删除回合

围绕回合 anchor（`anchor_msg_id`）做的一组互相配合的功能。后端模型用 `(anchor_msg_id, version)` 标识：`version=0` 是当前活跃版本，重放会把旧组整体推到 `version>=1`。

**hover 工具栏**

- assistant 气泡 hover 出现：复制 / 重放 / 上一版 / `当前位/总数` / 下一版
- user 气泡 hover 出现：编辑后重放（铅笔）、删除此回合（红色垃圾桶）
- streaming 期间所有按钮禁用

**重放（不改 PROMPT）**

- `regenerateChatMessage(sid, pid, anchor_msg_id, '', ...)` 第四参数为空 → 后端用 anchor 原 PROMPT
- 客户端把当前活跃 assistant 气泡内容清空、置 pending，SSE delta 直接覆盖填回去
- 完成后 `loadMessages()` 拉权威数据，重放出的新消息按 anchor 排在原回合位置

**编辑 PROMPT 后重放**

- `EditPromptDialog`：textarea 默认全选原 PROMPT，`Ctrl/⌘ + Enter` 提交，`Esc` 取消
- 提交时调 `regenerateChatMessage(sid, pid, anchor_msg_id, newPrompt, ...)`，乐观把 user 气泡更新为新内容、assistant 气泡进入 pending
- 后端写入新一组 `version=0` 共享同一 anchor，旧组（含旧 PROMPT）整体 `version+=1`

**版本切换**

- 仅当某 anchor 有多个版本时才显示左右箭头与 `当前位/总数`
- 客户端用 `displayedPosByAnchor: Record<anchor, pos>` 维护视觉位置（1=最新，N=最早）；切换时调 `switchMessageVersion(target_msg_id)`，后端做整组 swap（user / tool / assistant 同步对调，避免错位）
- 切换后 `loadMessages()` + 保留 displayedPos
- 跨页刷新会重置位置为 1（这是后端 swap 模型的固有限制——swap 后 `version=0` 永远是当前活跃）

**删除回合**

- 红色垃圾桶 → `ConfirmDialog` 二次确认 → `deleteTurn(anchor_msg_id)`
- 后端硬删 `anchor_msg_id = ? AND version = 0` 的整组（user 自身 + tool_call / tool_result / assistant）
- 历史版本（`version>=1`）保留，可用版本切换按钮调出
- 删完 `delete displayedPosByAnchor[anchor]` + `loadMessages()`

### 11. AI 模型配置

- 侧边栏「设置」按钮点击可打开 `AIConfigDialog`（已解除原有的禁用状态）。
- 支持列出当前用户创建的所有自定义模型配置。
- 支持创建、更新、删除模型配置，表单参数包括配置名称、API Key、Base URL、Model Name、系统指令、Temperature 和 Max Tokens。
- 支持激活/取消激活模型配置，实现对当前活跃配置的原子性切换。
- 支持一键连通性测试（Test Connection），可针对已保存的配置或临时填写的参数发送极简测试请求，验证 API 连通性。

## 尚未实现 / 有意省略

- 附件、图片、语音输入
- 多客户端会话广播、通知
- 侧边栏「文档 / 仪表盘」按钮仅占位、禁用点击（「设置」已激活用于 AI 模型配置）
- 通用文件浏览器 UI（目前文件 API 仅被 Skill 管理使用）
- 项目技能在对话框中增删后由 `useProjectSkills(pidRef)` composable 统一管理：ChatView 订阅 skills ref，App.vue 在对话框关闭时调 `refresh()`，无需额外事件总线
- 「跨页刷新后保持版本切换位置」：当前 `displayedPosByAnchor` 仅活在内存里，跨页刷新会重置为 1。要做绝对定位需要后端引入稳定的 branch_id，本期未做

## 开发与运行

```bash
# 安装
npm install

# 开发（默认代理后端 http://localhost:8000，可用 VITE_DEV_API_PROXY_TARGET 覆盖）
npm run dev

# 构建（会先 vue-tsc --noEmit 做类型检查）
npm run build

# 预览生产构建
npm run preview
```

环境变量：

| 名称 | 说明 |
|---|---|
| `VITE_API_BASE_URL` | 生产环境 API 前缀，默认空（相对路径） |
| `VITE_DEV_API_PROXY_TARGET` | 开发代理目标，默认 `http://localhost:8000` |

## 关键约定

- 所有后端调用必须经 `api.ts`，不要在组件里裸写 `fetch`
- 固定参数统一放在 `src/config/`，业务代码不要硬编码 magic number / magic string
- 跨视图共享状态走 `composables/*` 单例（模块级 `ref`），新增共享状态优先落在 composable 里；视图独占状态（messages / draft / streaming 等）留在视图组件 `<script setup>` 内，组件卸载即释放
- 新增路由：在 `router/index.ts` 的 `routes` 里加记录；静态 title 通过 `meta.title` 提供，动态 title 在视图内 `watch` 直接写 `document.title`
- 登录态保持条件渲染在 `App.vue` 顶层，不用路由守卫劫持；未登录访问受限路由时 URL 不变、登录后原地激活
- 技能名的正则和长度限制在 `config/skills.ts`（`skills.ts` 会继续导出），后端改约束时两边同步
- 新增 SSE 事件类型：在 `api.ts#streamLoop` 的 `parseSseFrame` 分支里处理，并把类型加入 `StreamEvent`
- Markdown 里新的自定义 fence 语言：改 `markdown/renderer.ts#md.renderer.rules.fence`，并在 `DOMPurify` 的 `ADD_TAGS` / `ADD_ATTR` 白名单里补齐
