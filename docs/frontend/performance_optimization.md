# 前端界面加载与渲染性能优化文档

本文档记录聊天页面首屏加载、长历史滚动、Markdown / LaTeX / Mermaid 渲染成本和异常同步的优化方案。

---

## 1. 核心优化项说明

### 1.1 移除冗余占位框

* **问题描述**：当会话无历史消息时，界面会弹出一个 dashed 边框提示“还没有消息”，在对话建立后又会被迅速挤掉，影响视觉一致性。
* **修改方案**：移除 `ChatView.vue` 中的“还没有消息”提示 DOM，空会话直接显示输入区。

### 1.2 引入 message block 本地缓存

* **问题描述**：长会话如果恢复完整消息正文，会把大量 Markdown、公式、代码块和 Mermaid 内容一次性带回内存并进入渲染队列；只缓存最近分页又无法让滚动条准确表达完整历史。
* **修改方案**：
  1. `localStorage` 按 `chat_cache_<sid>` 存储 `blockIndex`、已取过的 block 正文、附件、实测高度、版本快照和 `revision`。
  2. 缓存 schema 为 `CHAT_CACHE_SCHEMA = 3`，旧格式自动忽略。
  3. 后台刷新不再全量拉正文，而是用 block digest 增量同步；digest 变化或删除的 block 会同步清理正文缓存和高度缓存。
* **收益**：切换会话可先恢复轻量索引和已缓存正文，避免白屏；同时不会为了首屏展示读取整段历史正文。

### 1.3 首屏贴底与完整历史滚动条

* **问题描述**：聊天页面应始终从最新消息底部打开，但长历史又不能一次性挂载所有消息，否则首屏会被昂贵渲染拖慢。
* **修改方案**：
  1. 初始化调用 `GET /sessions/{sid}/message-block-index` 获取完整轻量索引和 `estimated_height`，不包含完整正文。
  2. 前端用索引估算每个 turn block 的高度，计算 `topSpacerHeight` / `bottomSpacerHeight`，让滚动条代表完整历史。
  3. `setVirtualWindowToBottom()` 将虚拟窗口定位到最后 `VIRTUAL_BLOCK_LIMIT` 个 block，随后 `scrollToBottom(true)` 强制贴底。
  4. `ResizeObserver` 在真实 DOM 渲染后记录实测高度，并写回高度缓存。
* **收益**：首屏稳定显示最新消息；滚动条从一开始就反映整个会话长度，而不是只代表已加载分页。

### 1.4 LaTeX 公式节流渲染

* **问题描述**：流式输出期间，每个字符增量都会触发 Markdown / LaTeX / Mermaid 重解析，导致公式闪烁和主线程卡顿。
* **修改方案**：
  1. `MessageContent.vue` 在 `streaming === true` 时用轻量 `throttle` 将内容增强频率限制到 `150ms` 一次。
  2. 流结束或非流式历史消息渲染时，立即执行同步无延迟的最终渲染，保证公式、复制按钮和 Mermaid 交互完整。
* **收益**：流式阶段的 DOM 重构次数显著下降，公式渲染更稳定。

### 1.5 出错与取消时的重试状态同步

* **问题描述**：流式报错或 STOP 取消时，后端可能已经落库了当前回合；如果前端只保留临时消息，就缺少真实 `anchor_msg_id`，重放和编辑后重放按钮会失效。
* **修改方案**：`sendMessage` 与 `regenerateMessage` 的正常完成、`done.error` 和 `catch` 出口均调用 `loadMessages(false)`。该函数通过 `message-block-delta` 刷新权威索引，再按需加载可见 block 正文。
* **收益**：异常或取消后无需刷新页面，用户仍能直接重试当前回合。

### 1.6 Turn-block 虚拟化渲染

* **问题描述**：按消息分页能降低网络负载，但滚动条只代表已加载消息；全量加载又会让长会话的 Markdown / LaTeX / Mermaid 同时进入渲染，浏览器容易卡死。
* **修改方案**：
  1. 后端按展示语义生成 turn block：一条或多条连续 `user` 消息 + 随后的 `assistant` 回复；工具调用和工具返回不展示。
  2. 前端固定虚拟窗口：`VIRTUAL_BLOCK_LIMIT = 10`，`VIRTUAL_BLOCK_OVERSCAN_PX = 720`；向下扩展时最多额外挂载约 4 个 block。
  3. 可见 block 缺正文时调用 `POST /sessions/{sid}/message-blocks` 批量加载；不可见 block 只保留索引和 spacer。
  4. `handleChatScroll()` 只更新虚拟窗口位置，不触发“加载上一页”式的数据拼接。
* **收益**：滚动条保持完整历史语义，同时把实际 DOM 和昂贵 Markdown 渲染限制在可视区附近。

### 1.7 右侧节点链导航

* **问题描述**：长会话虽然保留了完整原生滚动条，但原生滚动条无法直接表达“当前处于哪个对话回合”，也不能快速预览附近 turn block 的用户问题。
* **修改方案**：
  1. `ScrollNodeChain.vue` 作为 ChatView 的右侧辅助导航层，不替换原生滚动条。
  2. 组件一次性把所有 turn block 节点渲染进同一个内部 `node-track`，外层 `node-viewport` 只裁剪出可见节点段；滚动时只更新 `transform`，避免节点一格一格重绘跳动。
  3. `ChatView.vue` 用 `blockMetrics.offsets`、实测 block 高度和 `chatContainer.scrollTop` 计算连续的 `scrollNodeVirtualIndex`，中心聚焦节点跟随该小数索引移动。
  4. 中心聚焦节点使用暗紫色 `#4c1d95`；hover 节点会显示对应 block 的首条 user 消息，正文未缓存时通过 `ensureBlockContents([block.id])` 按需获取。
  5. 点击节点会调用 `scrollToMessageBlock(index)`，按当前 block offset 平滑滚动到对应回合。
* **收益**：右侧节点链提供回合级定位和预览，同时继续复用已有 block index / block content 缓存机制，不增加首屏正文加载量。

### 1.8 已知限制

* `estimated_height` 是后端估算值，真实高度会在图片 Blob URL、Markdown 二阶段渲染、LaTeX / Mermaid 完成渲染、版本工具栏出现后由 `ResizeObserver` 修正。
* 贴底状态下前端会继续保持底部；向上浏览历史时，如果某个 block 从估高切到实测高度，滚动位置可能出现轻微修正。

---

## 2. 代码实现位置参考

* [`ChatView.vue`](../../frontend/src/views/ChatView.vue)
  * `CHAT_CACHE_SCHEMA` / `CHAT_CACHE_PREFIX`：本地缓存版本和 key 前缀。
  * `blockIndex` / `blockContentCache` / `blockHeights`：轻量索引、正文缓存、实测高度缓存。
  * `messageBlocks` / `blockMetrics` / `topSpacerHeight` / `bottomSpacerHeight` / `virtualBlocks`：完整历史滚动高度与虚拟窗口计算。
  * `setVirtualWindowToBottom()` / `updateVirtualWindowFromScroll()`：初始化贴底和滚动时窗口移动。
  * `applyChatCache()` / `writeChatCache()`：缓存恢复和写入。
  * `applyFullBlockIndex()` / `applyBlockDelta()`：全量索引和 digest 增量同步，负责失效正文与高度缓存。
  * `ensureVisibleBlockContents()` / `ensureBlockContents()`：只为可见 block 拉取正文。
  * `measureVirtualBlock()`：通过 `ResizeObserver` 记录真实 block 高度。
  * `loadMessages(init)`：初始化走 block index，后续刷新走 block delta，并同步附件。
  * `scrollNodeItems` / `scrollNodeVirtualIndex` / `calculateScrollNodeVirtualIndex()`：右侧节点链的数据源和连续位置映射。
  * `handleScrollNodeHover()` / `scrollToMessageBlock()`：节点 hover 按需加载正文，节点点击平滑定位到 turn block。
* [`ScrollNodeChain.vue`](../../frontend/src/components/ScrollNodeChain.vue)
  * `node-track`：包含全部 turn block 节点，通过 `transform` 连续移动。
  * `node-viewport`：裁剪右侧可见节点段，避免视觉上显示全部节点。
  * `currentIndex`：把当前连续位置四舍五入为中心聚焦节点，使用暗紫色高亮。
  * `nodeTooltip`：hover 时独立显示用户消息预览，不参与节点轨道滚动。
* [`api.ts`](../../frontend/src/api.ts)
  * `MessageBlockIndexItem` / `MessageBlockIndexResponse` / `MessageBlockDeltaResponse` / `DisplayMessageBlock`：前端 block 协议类型。
  * `listMessageBlockIndex()`：调用 `GET /sessions/{sid}/message-block-index`。
  * `syncMessageBlockDelta()`：调用 `POST /sessions/{sid}/message-block-delta`。
  * `getMessageBlocks()`：调用 `POST /sessions/{sid}/message-blocks` 并复用 `parseMessage()` 转成展示消息。
* [`MessageContent.vue`](../../frontend/src/components/MessageContent.vue)
  * `throttle()`：流式阶段的轻量节流函数。
  * `watch(content)`：streaming 期间按 150ms 节流渲染。
  * `watch(streaming)`：流结束后同步收底。
