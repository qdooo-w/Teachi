# Teachi Frontend

基于 Vue 3 + Vite + Tailwind 的 AI 聊天前端，对接 FastAPI 后端，支持账号鉴权、科目与会话管理、SSE 流式对话、Markdown/LaTeX/Mermaid 渲染，以及用户级 / 项目级技能（Skill）的管理和按需挂载。

## 目录结构

```
frontend/
├─ index.html              Vite 入口 HTML，仅挂载 <div id="app">
├─ package.json            依赖与脚本（vite / vue / tailwind / katex / mermaid / markdown-it 等）
├─ vite.config.ts          开发代理：把 /auth /loop /users /projects /sessions /messages /tools /health 转发到后端
├─ tsconfig.json
├─ postcss.config.js       Tailwind v4 PostCSS 插件配置
└─ src/
   ├─ main.ts              createApp(App).mount('#app')，仅引入 style.css
   ├─ style.css            全局样式：Tailwind + KaTeX + highlight.js 主题 + 自定义 .markdown-body 作用域
   ├─ vite-env.d.ts        Vite 环境类型声明
   ├─ App.vue              单页应用根组件，承载全部视图、路由、聊天与技能状态
   ├─ api.ts               后端 HTTP 客户端：鉴权、资源 CRUD、SSE、文件 API
   ├─ skills.ts            Skill 领域逻辑：frontmatter 校验、结构化读写、SKILL.md 模板
   ├─ components/
   │  ├─ MessageContent.vue       Markdown 消息渲染与代码块复制、Mermaid 延迟渲染
   │  ├─ SkillChips.vue           已选技能的 chip 行（发送时随消息带走）
   │  ├─ SkillPicker.vue          @ 触发的技能下拉选择器，支持搜索与键盘导航
   │  └─ SkillManagerDialog.vue   用户级 / 项目级技能管理对话框（结构化表单 + 原始兜底）
   └─ markdown/
      ├─ renderer.ts       markdown-it 单例 + KaTeX + 代码块 / 链接 / mermaid 自定义渲染 + DOMPurify
      ├─ highlight.ts      highlight.js 按需注册语言
      └─ mermaid.ts        mermaid 懒加载与 DOM 内占位替换
```

## 模块依赖关系

```
main.ts
 └─ App.vue ───┬─ api.ts              所有后端调用的统一出口
               ├─ skills.ts           ── 依赖 api.ts 的通用文件 API
               ├─ components/MessageContent.vue
               │     └─ markdown/renderer.ts
               │           ├─ markdown/highlight.ts
               │           └─ markdown/mermaid.ts
               ├─ components/SkillChips.vue
               ├─ components/SkillPicker.vue
               └─ components/SkillManagerDialog.vue
                     └─ skills.ts
```

- `api.ts` 是所有后端通信的唯一出口，封装 `fetch` + 401 自动刷新、JWT 本地存储、SSE 帧解析、通用文件 API
- `skills.ts` 把 Skill 视为「`skills/<name>/SKILL.md` 文件」，业务层全部走 `api.ts` 的通用文件 API
- `markdown/` 三个文件是纯渲染层，不依赖后端
- `App.vue` 是唯一的状态容器：不引入 Vuex / Pinia，状态靠 `ref` / `reactive` + `computed` 组织

## 已完成的功能

### 1. 认证

- 登录 / 注册双模式切换（`/auth/login`、`/auth/register`），邮箱记忆到 `localStorage`
- Access token 存 `localStorage`，refresh token 由后端 HttpOnly Cookie 承载
- 启动时若本地有 token 直接进入；无 token 或已失效则尝试 `/auth/refresh`
- 401 自动刷新：`api.ts` 里任意请求命中 401 会静默调用 `/auth/refresh` 重试一次
- 登出清空所有本地状态并请求 `/auth/logout`

### 2. 科目与会话（导航三态）

`currentView` 在三个视图间切换：

| 视图 | 说明 |
|---|---|
| `overview` | 科目总览：卡片列表 + 底部「输入科目名直接新建」 |
| `subject` | 某科目下的历史会话列表 + 底部「输入首条消息 → 自动新建会话并发送」 |
| `chat` | 具体会话的消息流 + 输入框 |

- 侧边栏显示最近 10 个科目，含「查看全部」跳回 `overview`
- 顶栏是面包屑（科目 / 会话名）
- 响应式：宽度 < 768px 切换到移动端布局，侧边栏变浮层 + 遮罩

### 3. 聊天主循环（SSE）

- `POST /loop/{sid}`，`action=send` / `stop`，请求头必带 `Authorization` + `X-Nonce` + `X-Nonce-Timestamp`
- 用 `fetch` + `ReadableStream` 读 SSE，自己按 `\n\n` 分帧，比 `EventSource` 多了携带 body 和自定义头的能力
- 处理的帧类型：
  - `text_delta` —— 拼接到当前 assistant 消息的 content 并触发自动滚动
  - `tool_call` —— 在输入框上方显示「正在调用 XX」
  - `tool_result` —— 清除工具状态
  - `done` —— 携带 `msg_id`（成功）或 `error` / `error_code`（失败）
- 发送后立即乐观 push 一条 `pending: true` 的 assistant 占位气泡，收到 `done` 后再 `loadMessages()` 拉服务端权威版本
- 「停止生成」：调用 `POST /loop/{sid}` 带 `action=stop`，同时 `AbortController.abort()` 关闭前端 SSE
- 自动贴底滚动：监听容器 scroll，只有用户停留在底部（阈值 32px）时才自动贴底

### 4. Composer 交互

- 输入框高度随内容自适应（44px ~ 240px）
- `Ctrl/⌘ + Enter` 发送，`Enter` 换行
- `@` 触发 `SkillPicker`：从光标向前匹配 `@xxx` 就展开抽屉
- `SkillPicker` 支持搜索（name + description）与上下 / Enter / Esc 键盘导航
- 选中技能后在输入框上方显示 chip，可 × 移除；发送时自动拼前缀 `[本轮请优先考虑使用技能：xxx、yyy]\n\n<原始内容>`

### 5. 技能管理（Skill）

Skill 在后端就是 `skills/<name>/SKILL.md` 的文件约定，前端完全通过通用文件 API 读写。

`SkillManagerDialog` 支持：

- 左栏列表 + 「新建技能」按钮
- 右栏结构化表单：
  - `name`（受限 `^[a-z0-9]+(-[a-z0-9]+)*$`，长度 ≤ 64，不含保留词 `anthropic` / `claude`）
  - `description`（≤ 1024）
  - `license`、`compatibility`（≤ 500）作为高级字段折叠
  - `body` 仅提示字符 / 行数，不做硬限制
- 正文前端侧限制 128 KB
- 旧文件 frontmatter 无法结构化解析时自动降级为「原始编辑」模式，保存前仍做 frontmatter 合法性兜底校验
- `yaml.stringify` 生成 frontmatter，避免人工漏空格之类 YAML 陷阱

「我的技能」（用户级）和「项目技能」（项目级）共用同一对话框，靠 `FileSpace` 判别：

```ts
type FileSpace =
  | { kind: 'user'; userId: string }
  | { kind: 'project'; pid: string }
```

对应后端路径 `/users/{user_id}/files` 或 `/projects/{pid}/files`。

### 6. Markdown / 代码 / 数学 / Mermaid 渲染

`MessageContent.vue` + `markdown/renderer.ts` 流水线：

1. `markdown-it` 单例：`html: false` + `linkify: true`，链接强制 `target="_blank"` + `rel=noopener noreferrer nofollow`
2. `markdown-it-texmath` + KaTeX：支持 `$...$` / `$$...$$` / `\(...\)` / `\[...\]`
3. 自定义 `fence` 规则：
   - `mermaid` 语言 → 输出 `<pre data-lang="mermaid" data-source="...">` 占位，流式结束后由 `mermaid.ts` 懒加载替换为 SVG
   - 其它语言 → `highlight.js` 着色，包一层 `.code-block` 头 + 「复制」按钮
4. DOMPurify 兜底：打开 html / svg / mathMl 白名单，放行 KaTeX 的 `eq / eqn / section` 和自定义的 `data-*` 属性
5. 消息容器里挂 click 代理，把 `[data-copy]` 按钮接上复制 → 「已复制」1.5s 反馈

Mermaid 渲染失败降级为可见的 error 卡片而不是白屏。

### 7. 消息历史

- `GET /sessions/{sid}/messages` 拉原始 PydanticAI `ModelMessage` 序列化数据
- 前端只渲染 `is_latest === 1` 的条目
- 解析逻辑在 `api.ts#parseMessage`：
  - `kind === 'user'` + `parsed.kind === 'request'` → 取 `user-prompt` 部分
  - `kind === 'assistant' | 'agent_response'` + `parsed.kind === 'response'` → 取 `text` 部分
  - 工具调用 / 返回类消息在前端不展示

### 8. 其它

- 消息复制：鼠标悬停 assistant 气泡左下显示复制按钮，带 1.5s 视觉反馈
- 错误体 → 文案：`api.ts#getErrorMessage` 兼容 `ApiError` / `Error` / `{ detail: ... }` / `{ detail: { message } }`

## 尚未实现 / 有意省略

- 消息级 regenerate、版本切换（后端已支持 `/messages/{msg_id}/versions`、`/messages/{msg_id}/switch-version`，UI 未接）
- 附件、图片、语音输入
- 会话重命名 / 删除；项目重命名 / 删除
- 多客户端会话广播、通知
- 侧边栏「文档 / 仪表盘 / 设置」按钮仅占位、禁用点击
- 通用文件浏览器 UI（目前文件 API 仅被 Skill 管理使用）

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
- 技能名的正则和长度限制在 `skills.ts` 顶部，后端改约束时两边同步
- 新增 SSE 事件类型：在 `api.ts#streamLoop` 的 `parseSseFrame` 分支里处理，并把类型加入 `StreamEvent`
- Markdown 里新的自定义 fence 语言：改 `markdown/renderer.ts#md.renderer.rules.fence`，并在 `DOMPurify` 的 `ADD_TAGS` / `ADD_ATTR` 白名单里补齐
