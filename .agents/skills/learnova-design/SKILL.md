---
name: learnova-design
description: 在为 Learnova 项目开发或修改前端组件时调用此技能，以确保所有 UI 严格符合项目的既定设计语言、色彩规范与交互动效体系。
---

# Learnova 深度设计语言规范 (Design Language Guidelines)

在开发、修改前端组件或页面布局时，请务必严格遵守以下视觉与交互规范。项目基于 Vue 3 + Tailwind CSS v4，深度融合了极简黑白灰风格与毛玻璃质感，完全依靠内建类名实现高度一致的设计系统。

## 1. 核心色彩体系 (Dual Color Systems)

本项目独特地采用了**双线中性色系统**：主界面使用硬编码的 Hex 灰度值，而各类高级弹窗（如设置页、技能管理器）则大量切换为 Tailwind 原生的 `slate` 蓝灰系列，以区分空间层级。

### 1.1 主应用域 (Main UI Hex 灰度)
- **背景 (Backgrounds)**: `bg-[#f3f4f6]` (全局底色), `bg-[#ffffff]` (主卡片/侧边栏), `bg-[#e5e7eb]` (用户聊天气泡)
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
- **用户消息**: `rounded-3xl border border-[#d1d5db] bg-[#e5e7eb] px-5 py-3 text-[15px]` (浅灰底，带边框)。
- **AI 消息**: `rounded-3xl bg-white px-5 py-4 text-[15px]` (纯白底，无边框，更宽敞的 padding)。
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
- **滚动安全高度**: 消息滚动区容器内部的底部内边距调整为大 padding（例如 `pb-52` / `208px`），确保最后一条消息能够完全向上滚出悬浮框的遮挡高度，不被永久遮挡。

### 4.4 弹窗对话框规范 (Modal Dialogs)
- **字体族继承**: 所有的对话弹窗（包括 `ConfirmDialog`, `EditPromptDialog`, `SettingsDialog`）必须在最外层卡片包裹层（`.modal-card`）上全局加上 `.font-hans` 类，以实现弹窗内文案、提示与按钮等字体的高度统一。

### 4.5 操作菜单与轻量选项 (Popover Actions / RowMenu)
- **极简紧凑尺寸**: 侧边栏等狭窄区域的项目操作菜单（如 `RowMenu` 弹出的重命名/删除面板）应保持极致紧凑的微观排版。卡片最小宽度设为 `min-w-[100px]`，外壳使用 `py-1 border border-[#d1d5db] bg-white rounded-lg shadow-lg`，并加上 `.font-hans` 类。
- **微型文本与边距**: 面板内按钮与文字统一采用 `text-xs`，单项 padding 采用 `px-2.5 py-1.5`，间距使用 `gap-1.5`，修饰图标尺寸缩至 `h-3.5 w-3.5`，以避免空间拥挤，在小空间内营造高级且呼吸感充足的视觉体验。

### 4.6 悬浮预览窗口 (Floating Preview Windows)
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

## 5. 动效与交互反馈 (Animations & Feedback)

- **物理按压反馈**: 所有主要操作按钮必须带上按压微缩放效：`active:scale-95 transition-all duration-200`。
- **打字指示器 (Typing Indicator)**: 使用 3 个 `animate-bounce` 配合不同 `animation-delay` 的圆点。
- **特制路由/弹窗抽屉**:
  - 弹窗显示：使用 Vue `<Transition name="dialog-fade">` (结合了 `scale(0.96)` 与淡入)。
  - 路由推拉：使用 `view-slide-forward` 和 `view-slide-backward`。
- **缓动函数**: 关键动画使用自定义贝塞尔曲线 `cubic-bezier(0.2, 0.8, 0.2, 1)`（160-220ms）。
- **发光态 (Glow)**: AI 生成态的输入框应用了 CSS `@property` 配合 `conic-gradient` 实现围绕边缘旋转的呼吸流光。

## 6. 无障碍设计 (Accessibility)

- **语义与键盘**: 非标准可点击元素须添加 `role="button"` 和 `tabindex="0"`，支持 `@keydown.enter`。
- **自定义焦点**: 禁用浏览器默认轮廓 `outline-none`，永远使用上述的 Focus Ring。
- **SVG 图标**: 修饰性图标必须加 `aria-hidden="true"`。
