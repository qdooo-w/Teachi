---
name: learnova-design
description: 在为 Learnova 项目开发或修改前端组件时调用此技能，以确保所有 UI 严格符合项目的既定设计语言、色彩规范与交互动效体系。
---

# Learnova 深度设计语言规范 (Design Language Guidelines)

在开发、修改前端组件或页面布局时，请务必严格遵守以下视觉与交互规范。项目基于 Vue 3 + Tailwind CSS v4，深度融合了极简黑白灰风格与毛玻璃质感，完全依靠内建类名实现高度一致的设计系统。

## 1. 核心色彩体系 (Dual Color Systems)

本项目独特地采用了**双线中性色系统**：主界面使用硬编码的 Hex 灰度值，而各类高级弹窗（如设置页、技能管理器）则大量切换为 Tailwind 原生的 `slate` 蓝灰系列，以区分空间层级。

### 1.1 主应用域 (Main UI Hex 灰度)
- **背景 (Backgrounds)**: `bg-[#f3f4f6]` (全局底色), `bg-[#ffffff]` (主卡片/侧边栏), `bg-[#ffffff]` (用户聊天气泡)
- **文本 (Text)**: `text-[#1f2937]` (主文本), `text-[#4b5563]` (次文本), `text-[#9ca3af]` (禁用/占位符)
- **边框 (Borders)**: `border-[#d1d5db]` (实体卡片), `border-[#e5e7eb]` (柔和分割线)
- **主操作 (Primary Action)**: `bg-[#1f2937] hover:bg-[#111827]`
- **焦点环 (Focus Ring)**: `focus-within:ring-2 focus-within:ring-[#1f2937]/20` 或 `focus:ring-2 focus:ring-[#1f2937]/20`

### 1.2 弹窗/模态域 (Modal UI Slate 蓝灰)
在 `SettingsDialog`, `SkillManagerDialog` 等复杂弹窗中，全面改用 `slate` 调色板：
- **背景**: `bg-slate-50/50` 或 `bg-slate-50/80` (配合毛玻璃使用)
- **文本**: `text-slate-700` (标题), `text-slate-600` (正文), `text-slate-400` (极弱文本)
- **边框**: `border-slate-100`, `border-slate-200/80`
- **主操作**: `bg-slate-900 text-white hover:bg-slate-800`

### 1.3 交互与状态色 (States)
- **警示红 (Destructive Hover)**: 危险操作（如删除）悬停时使用 `hover:bg-[#fee2e2] hover:text-[#b91c1c]` (红底红字)。
- **错误提示**: 背景 `bg-[#fff7ed]`，边框 `border-[#efb3a7]`，文本 `text-[#9a3412]`。
- **高亮蓝紫 (Window Highlight Accent)**: 在媒体预览窗口激活/高亮提示时，使用蓝紫色高亮修饰：`border-indigo-500 ring-4 ring-indigo-500/20`。

## 2. 空间层级与毛玻璃效果 (Glassmorphism & Z-Index)

Learnova 大量依靠透明度与背景模糊（Backdrop Blur）来构建悬浮感与纵深感。

- **全局遮罩 (Overlay)**: 所有 Dialog 必须使用黑色半透明叠加毛玻璃：`bg-black/40 backdrop-blur-sm`。
- **悬浮控件 (Floating Controls)**: 页面悬浮操作栏（如媒体预览器控制条）使用高斯模糊：`bg-white/10 backdrop-blur-md`。
- **悬浮顶栏与按钮 (Floating Header & Controls)**:
  - 顶栏容器 (`<header>`) 采用绝对定位 `absolute` 且背景完全透明，并添加 `pointer-events-none` 允许非控制区的点击/交互穿透。
  - 顶栏内部的左右按钮区域（如侧边栏开关、标题栏、功能按钮等）使用独立的悬浮药丸卡片容器包裹，样式为 `pointer-events-auto bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-[#e5e7eb] shadow-sm`，按钮元素本身也采用圆形 `rounded-full` 极简视觉。
- **Z-Index 规范**: 
  - 侧边栏/局部遮罩：`z-40` 或 `z-50`
  - 通用弹窗：`z-[100]` 或 `z-[110]`
  - 高优先级全屏弹窗（如 SkillManager）：`z-[1000]`

## 3. 圆角与边缘 (Radii & Edges)

崇尚圆润、无锐角的现代设计哲学，容器与内部元素的圆角必须保持同心协调。
- **超大圆角**: `rounded-3xl` (专门用于聊天气泡，营造亲和力)。
- **巨型圆角**: `rounded-2xl` (侧边栏项、底部输入区外壳、发送按钮)。
- **大/中等圆角**: `rounded-xl` 或 `rounded-lg` (弹窗主体、工具调用卡片、输入框)。

## 4. 核心组件结构解析 (Component Anatomy)

### 4.1 聊天气泡 (Chat Bubbles)
- **用户消息**: `rounded-3xl bg-white px-4 py-2 text-[15px]` (纯白底，无边框)。
- **AI 消息**: `bg-[#f3f4f6] px-4 py-3 text-[15px]` (背景色平铺，无独立卡片底色与圆角)。
- **工具调用卡片 (Tool Calls)**: `rounded-xl border border-[#d1d5db] bg-white p-3 shadow-sm max-w-[240px]`。
- **隐藏式操作栏 (Hover Actions)**: 气泡旁的复制/刷新等按钮默认隐藏，靠父级 `group` 控制显示：`opacity-0 group-hover:opacity-100 transition-opacity text-[#9ca3af] hover:text-[#4b5563]`。

### 4.2 输入框外壳 (Composer Shell)
- **焦点环与边框**: 输入框外壳（与新建科目、新建会话等输入面板）采用常驻灰色细边框 `border border-neutral-200 bg-white`。在选中/聚焦（`focus-within`）时，**取消周边的环绕阴影**（不使用 `ring` 和 `shadow` 等高光），只保持实体细边框，提供极简纯净的交互体验。
- **字体与排版规范**: 所有对话输入面板（包括新建科目描述、新建会话和常规消息输入框）在最外层（如 `create-panel-wrapper` 或组件根元素）必须套用 `font-hans` 字体族类，以确保在**展开和非展开状态下**内部所有的文本、占位符均继承统一的 `font-hans` 样式。文本默认使用次要文本色 `text-[#4b5563]`，占位符使用 `placeholder:text-[#9ca3af]`。
- **发送按钮状态转移**: 发送按钮禁用时变为幽灵态 `disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]`（或在新建科目和新建会话中，以图标置灰 `disabled:text-[#9ca3af]` 的形式表现）。

### 4.3 悬浮输入与滚动穿透 (Floating Composer & Scroll-Through)
为了让界面整体充满呼吸感与纵深空间，对话界面采用了悬浮式的输入面板设计：
- **悬浮定位**: 底部输入框（`composer-shell`）处于绝对贴底悬浮状态。外层使用 `pointer-events-none` 允许交互穿透，内部控制面板使用 `pointer-events-auto` 接收点击。输入框四周均留有适当间距（如底部 `pb-4` 与两侧 `px-4 md:px-6`），使消息列表能自然滑过输入框的下方和左右侧，使输入框下边也能清晰看到消息。
- **取消底遮挡**: 移除底部一切不透明的整宽渐变，允许底部的消息流畅无阻地绘制到最底层。
- **滚动安全高度**: 消息滚动区容器内部的底部内边距调整为大 padding（例如 `pb-32` / `128px`），确保最后一条消息能够完全向上滚出悬浮框的遮挡高度，不被永久遮挡。

### 4.4 弹窗对话框规范 (Modal Dialogs)
- **字体族继承**: 所有的对话弹窗（包括 `ConfirmDialog`, `EditPromptDialog`, `SettingsDialog`）必须在最外层卡片包裹层（`.modal-card`）上全局加上 `.font-hans` 类，以实现弹窗内文案、提示与按钮等字体的高度统一。

### 4.5 操作菜单与轻量选项 (Popover Actions / RowMenu)
- **极简紧凑尺寸**: 侧边栏等狭窄区域的项目操作菜单（如 `RowMenu` 弹出的重命名/删除面板）应保持极致紧凑的微观排版。卡片最小宽度设为 `min-w-[100px]`，外壳使用 `py-1 border border-[#d1d5db] bg-white rounded-lg shadow-lg`，并加上 `.font-hans` 类。
- **微型文本与边距**: 面板内按钮与文字统一采用 `text-xs`，单项 padding 采用 `px-2.5 py-1.5`，间距使用 `gap-1.5`，修饰图标尺寸缩至 `h-3.5 w-3.5`，以避免空间拥挤，在小空间内营造高级且呼吸感充足的视觉体验。

### 4.6 技能侧边栏与内联编辑器 (Skill Sidebar & Editor)

技能侧边栏（`ChatSkillSidebar`）和内联编辑器（`SkillEditorPanel`）在 chat 和 subject 路由下均可用。

- **侧边栏切换按钮**：右上角固定按钮组中，技能侧边栏切换按钮在 chat / subject 路由下均显示
- **关闭编辑按钮**：仅在 chat 路由下显示，subject 路由下编辑器通过侧边栏切换按钮关闭
- **SkillEditorPanel 无独立标题栏**：关闭功能统一由 App.vue 顶栏按钮提供，编辑器内部不包含关闭按钮
- **滑入滑出动画**：编辑器使用 `<Transition name="skill-editor">` 实现，从左侧滑入（`translateX(-100%→0)`），向右滑出（`translateX(0→100%)`），时长 300ms enter / 250ms leave

### 4.7 悬浮预览窗口 (Floating Preview Windows)
- **多开上限与层级**: 最多支持同时打开 8 个预览窗口。层级设为 `z-[120]`，当某个窗口被点击时，需要将其移至 `activePreviews` 数组的末尾，以动态维持最新的置顶层级。
- **边界限制**: 窗口位置通过在拖拽与缩放时进行边界检测进行严格限制，位置与尺寸始终保持在 `[0, innerWidth - windowWidth]` 和 `[0, innerHeight - windowHeight]` 的视口内部，任何部分都不允许超出视口。
- **停靠与贴边状态 (Edge Docking)**:
  - 窗口接触视口边缘时（X 坐标或 Y 坐标为 0 或达到视口最大可用宽度/高度），激活贴边属性。
  - **单向贴边轴锁定**: 贴合纵向边缘（顶/底）时只记录水平相对位置比率 (`relX`)；贴合横向边缘（左/右）时只记录垂直相对位置比率 (`relY`)。双向贴角时不记录任何相对比例。
  - **视口自适应机制**: 当视口大小调整 (`resize` 触发) 时，被贴边的轴应始终牢牢固定在贴边边缘（如 `x = 0`），未贴边的轴则依据 `relX`/`relY` 的百分比进行同比缩放与自适应重定位，确保多屏/不同分辨率下窗口布局的协调。
- **挂起/折叠机制 (Window Suspension)**:
  - 窗口标题栏右上角（关闭按钮左侧）提供挂起按钮（`-` 符号），点击可将窗口临时挂起（状态标记为 `minimized: true`）。
  - 在窗口管理抽屉 (`WindowManager`) 中提供 `-`（挂起）或 `+`（还原）的快捷切换选项。已挂起的项目采用 `opacity-65 bg-neutral-50/30` 样式淡化，并附加 `已挂起` 状态标签以示区分。
  - 页面上针对挂起窗口使用 `v-show` 进行视觉隐藏，再次还原时能够完全保留窗口先前的缩放大小、画布滚动与偏移量等内部状态。

### 4.8 聊天节点链导航 (Scroll Node Chain)

聊天页右侧可以提供 turn-block 级别的辅助节点链，但必须作为原生滚动条之外的导航层，而不是替代滚动条。

- **原生滚动条保留**：节点链只表达回合位置与快速跳转，不隐藏、不替换浏览器原生滚动条。
- **连续轨道结构**：所有 turn block 节点应放入同一个内部 `node-track`，外层 `node-viewport` 只负责裁剪可见节点段；滚动时通过连续 `transform` 移动轨道，禁止每次 active index 变化就销毁并重建可见节点窗口，以免产生一格一格跳动。
- **节点样式**：节点使用极短横线刻度，默认 `#d1d5db` 灰色；中心聚焦节点使用暗紫色 `#4c1d95`，高度略增但仍保持克制。非聚焦 hover / focus 可以变为 `#111827` 并稍微加长。
- **无按钮默认外观**：节点按钮必须 reset `appearance`、`border`、`background`、`padding`，避免出现浏览器默认灰色按钮容器。
- **Tooltip 展示**：hover 节点时在横线左侧显示对应 turn block 的首条 user 消息，白底、细边框、轻阴影、单行省略；tooltip 应独立于滚动轨道定位，不参与 `node-track` 滚动，避免滚动时文字框抖动。
- **数据来源**：节点链复用 ChatView 的 `messageBlocks`、`blockMetrics` 和按需正文缓存。正文未缓存时可通过现有 block content 加载流程补齐，不应为节点链新增专用后端接口。

## 5. 动效与交互反馈 (Animations & Feedback)

- **物理按压反馈**: 所有主要操作按钮必须带上按压微缩放效：`active:scale-95 transition-all duration-200`。
- **打字指示器 (Typing Indicator)**: 使用 3 个 `animate-bounce` 配合不同 `animation-delay` 的圆点。
- **特制路由/弹窗抽屉**:
  - 弹窗显示：使用 Vue `<Transition name="dialog-fade">` (结合了 `scale(0.96)` 与淡入)。
  - 路由推拉：使用 `view-slide-forward` 和 `view-slide-backward`。
  - 技能编辑器滑入滑出：使用 `<Transition name="skill-editor">`，从左侧滑入、向右滑出（300ms/250ms）。
- **缓动函数**: 关键动画使用自定义贝塞尔曲线 `cubic-bezier(0.2, 0.8, 0.2, 1)`（160-220ms）。
- **发光态 (Glow)**: AI 生成态的输入框应用了 CSS `@property` 配合 `conic-gradient` 实现围绕边缘旋转的呼吸流光。

## 6. 无障碍设计 (Accessibility)

- **语义与键盘**: 非标准可点击元素须添加 `role="button"` 和 `tabindex="0"`，支持 `@keydown.enter`。
- **自定义焦点**: 禁用浏览器默认轮廓 `outline-none`，永远使用上述的 Focus Ring。
- **SVG 图标**: 修饰性图标必须加 `aria-hidden="true"`。

## 7. 全局通知与错误处理规范 (Global Notification & Error Handling)

项目已建立统一的全局通知系统，**严禁各组件重复实现 Toast/通知功能**，必须复用现有基础设施。

### 7.1 全局通知系统架构

- **逻辑层**: `useNotification` composable（`frontend/src/composables/useNotification.ts`）
- **视图层**: Toast 渲染代码位于 `App.vue` 模板底部（黑底白字浮动条，带毛玻璃效果）
- **错误解析**: `getErrorMessage()` 函数（`frontend/src/api.ts`）统一提取错误消息

### 7.2 复用方式

```typescript
// 在组件中导入并使用
import { useNotification } from '@/composables/useNotification'
import { getErrorMessage } from '@/api'

const { showSuccess, showError } = useNotification()

// 成功提示
showSuccess('操作成功')

// 错误提示（带详情展开）
try {
  await someApiCall()
} catch (err) {
  showError('操作失败', getErrorMessage(err))
}
```

### 7.3 使用场景规范

| 场景 | 实现方式 |
|---|---|
| API 调用成功/失败反馈 | 使用全局 `showSuccess` / `showError` |
| 表单提交结果 | 使用全局通知 |
| 多条并行操作结果 | 使用全局通知（自动堆叠） |
| 弹窗内的局部表单验证 | 使用组件内 `errorMsg` ref 行内展示 |
| 弹窗内的 API 错误 | 使用全局 `showError` 通知 |

### 7.4 通知样式（参考 App.vue）

Toast 位于页面顶部居中（`fixed top-14 left-1/2 z-[9999]`），采用：
- **背景**: `bg-neutral-950/95 backdrop-blur-md`（黑底毛玻璃）
- **成功图标**: 绿色勾 `text-emerald-400`
- **错误图标**: 红色叉 `text-red-400`
- **详情面板**: 可展开的 `<pre>` 代码块显示完整错误信息
- **动画**: `toast-slide` Transition（translateY + scale + opacity）

### 7.5 禁止事项

- ❌ 禁止在组件内自行实现 Toast / 通知堆叠逻辑
- ❌ 禁止使用 `alert()` 或浏览器原生弹窗
- ❌ 禁止重复定义通知样式（颜色、位置、动画）
- ✅ 弹窗内的行内错误提示（`errorMsg` ref + 红色背景文字）是允许的，用于表单级即时反馈

## 8. 社区技能广场设计规范 (Community Skill Hub)

### 8.1 整体布局

社区界面采用**无白色容器**的沉浸式设计，页面背景 `bg-[#f3f4f6]` 直接暴露，元素通过边框和间距区分层级。

```
┌──────────────────────────────────────────────────────────┐
│  🔍 搜索框 (h-8, rounded-2xl, bg-[#e5e7eb]/70)          │  ← 顶栏
├──────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────────────┐                       │
│  │ 主界面   │ │ skill-name      │                       │  ← 浏览器式标签栏
│  └──────────┘ └──────────────────┘                       │
├──────────────────────────────────────────────────────────┤
│  [排序 ▼] [🏷 标签]  [tag ×] [___]     共 N 个技能       │  ← 筛选栏 (bg-white)
├──────────────────────────────────────────────────────────┤
│  skill item 1                                            │
│  ────────────────────────────────────────────────────    │
│  skill item 2                                            │  ← 横线分隔列表
│  ────────────────────────────────────────────────────    │
└──────────────────────────────────────────────────────────┘
```

### 8.2 标签栏 (Browser-style Tabs)

- **容器**: `flex items-end gap-0.5 bg-transparent px-6 overflow-x-auto no-scrollbar`
- **标签按钮**: `px-2.5 py-1 !text-[13px] leading-none font-normal rounded-t-lg font-hans`
- **激活态**: `bg-white text-[#1f2937]`
- **未激活态**: `bg-transparent text-[#6b7280] hover:text-[#1f2937] hover:bg-[#e5e7eb]/60`
- **关闭按钮**: 仅技能标签显示 ×，主界面标签不可关闭
- **持久化**: 标签状态存入 `sessionStorage`，5 小时未访问自动清除

### 8.3 小顶栏 (Top Bar) — 硬性规范

**所有标签页（main / skill / import-console / pending-import）必须有一个小顶栏**，紧贴标签栏下方，作为该标签页的全局信息区。

- **容器**: `flex flex-shrink-0 items-center gap-2 px-5 py-2 bg-white font-hans`
- **高度由内容撑开**，不设固定 `h-*`，但通过 `py-2` 保证紧凑
- **内容规范**:
  - 主标题/关键信息用 `!text-xs font-semibold text-[#1f2937]`
  - 辅助描述用 `!text-xs text-[#9ca3af]`
  - 操作按钮（如删除、取消选择）用纯文字链接风格 `!text-xs text-red-500 hover:text-red-700 hover:underline`
  - 右侧用 `<div class="flex-1" />` 撑开，将操作/统计推到右端
- **各标签页的顶栏职责**:
  - **主界面 (main)**: 筛选控件（排序、标签）+ 多选时的操作按钮 + 技能总数统计
  - **技能详情 (skill)**: 技能名 + 来源标签（社区/本地）
  - **导入控制台 (import-console)**: 标题 + 一行简要说明
  - **待配置表单 (pending-import)**: 技能名 + 来源类型 + 放弃导入按钮

### 8.4 筛选栏 (Filter Bar)

筛选栏是主界面小顶栏的内部内容，遵循以下控件规范：
- **控件统一规范**:
  - 高度: `h-7` (28px)
  - 字体: `!text-xs` (12px, 需 `!` 强制覆盖全局 `font: inherit`)
  - 字体族: `font-hans` (思源黑体)
  - 边框: `border-0 border-b-2` (无四周边框，仅底部下划线)
  - 默认下划线色: `border-[#e5e7eb]`
  - hover 下划线色: `hover:border-[#1f2937]`
  - 左对齐: `pl-0`，内边距靠右 `pr-3`/`pr-4`
  - 无圆角: `rounded-none`
- **Sort 下拉**: 原生 `<select>`，去掉默认箭头用自定义 SVG
- **标签筛选按钮**: 点击切换标签输入模式，激活态 `border-[#1f2937] text-[#1f2937]`
- **标签 Chip**: `bg-[#e5e7eb] rounded-sm px-2`，带 × 移除按钮
- **标签输入框**: `w-32`，输入标签名回车添加

### 8.4 技能列表

- 列表项间用 `border-b border-[#e5e7eb]` 横线分隔，最后一项 `last:border-b-0`
- 每项 `py-4` 纵向间距，hover 时 `bg-[#f3f4f6]/50`
- 每页 15 条，翻页按钮使用 `h-8 w-8 rounded-lg` 数字按钮

### 8.5 技能详情页 (Skill Detail)

- **左右分栏**: `flex flex-col lg:flex-row`，左侧 README（flex-1），右侧元信息（`lg:w-[300px]` flex-shrink-0）
- **无 README 时**: 父容器不加 `lg:h-full`，左侧自动缩限高度，居中显示"暂无 README 内容"
- **元信息卡片**: `grid grid-cols-[60px_1fr] gap-x-3 gap-y-1.5` 标签-值对齐
- **评论区**: 两层嵌套（顶级评论 + 回复），评论卡片 `rounded-xl border bg-transparent`

### 8.6 标签页状态管理

- 标签列表 + 技能详情数据使用模块级变量保持路由切换不丢失
- 关闭标签时立即清除对应 `skillCache` 释放内存
- 每 10 分钟扫描一次，超过 5 小时未访问的标签自动关闭并清缓存
