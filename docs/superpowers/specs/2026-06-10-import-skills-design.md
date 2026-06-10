# Spec: Learnova 技能仓库导入控制台与队列配置表单设计

该 Spec 详细定义了 Learnova 技能仓库导入机制的交互规范、前端组件结构及后端 API 的扩展设计。本设计旨在使用户能够通过批量 ZIP 上传或运行层选择快速将技能导入个人技能仓库 (Library)，并通过与全局标签页 (Tab) 系统的无缝融合，提供沉浸式的元数据确认与模板化编辑体验。

---

## 一、 核心架构设计

### 1. 三层架构中的数据与文件流转
* **源数据解析**：
  * **运行层 (Runtime)**：从 `skills/{name}` 目录中读取 `SKILL.md` 的 frontmatter 进行字段解析。
  * **ZIP 上传 (Upload)**：接收 ZIP 二进制流，由后端临时解压校验并解析 `SKILL.md`，初步在 `user_library_skills` 数据库中创建记录，并提取 ZIP 内的 `README.md`。
* **数据保存流**：
  * 数据库元数据 (`display_name`, `description`, `tags`) 写入 `user_library_skills` 表。
  * 详细文档 (`readme_md`) 同步写回数据库，同时将物理文件 `README.md` 写入 `data/{user_uuid}/library/{library_id}/README.md`。

---

## 二、 前端交互与界面设计

### 1. 全局标签页系统的无缝融合
本设计直接复用仓库页面 (`LibraryView.vue`) 已有的全局 `tabs` 状态。
* **Tab 接口扩展 (`Tab` interface)**：
  ```typescript
  interface Tab {
    id: string
    type: 'main' | 'skill' | 'import-console' | 'pending-import'
    label: string
    skillId?: string          // type='skill' 时关联的已保存技能 ID
    pendingData?: {           // type='pending-import' 时暂存的配置上下文
      libraryId: string       // 后端初步入库生成的 UUID
      name: string            // 技能英文名标识
      displayName: string     // 初始解析出的显示名
      readmeMd: string        // 初始 README 内容
      source: 'zip' | 'runtime'
    }
    lastAccessed: number
  }
  ```
* **Tab 头部的视觉反馈**：
  如果 `tab.type === 'pending-import'`，在标签页名称的左侧渲染一个**紫色闪烁小圆点 `●`**，明确提示该技能处于待配置、尚未正式归入仓库的临时状态。

### 2. 导入控制台 (Import Console) —— 常驻标签页
作为全局 `tabs` 的一个常驻选项卡，用于批量导入的入口与队列管理。
* **布局与元素**：
  * **源选择组件**：
    * `ZIP 拖拽上传`：支持多 ZIP 文件并发拖入或点击上传。
    * `从运行层导入`：一个**可搜索且支持多选的 Combobox 下拉框**，列出本地运行层中尚未导入仓库的技能（通过 `GET /library/skills/unimported` 过滤）。
  * **解析队列 (Queue List)**：
    * 列表展示当前正在处理的任务。每项包含：`技能名`、`来源`、`文件大小`、`状态 (待解析 / 解析中 / 校验失败 / 解析成功)`。
  * **队列流转动作**：
    * 当 ZIP 上传成功或运行层解析成功后，任务状态置为「解析成功」。
    * 用户点击底部的**「开始配置并清空队列」**按钮：
      1. 清空控制台的待处理队列列表。
      2. 前端根据解析成功的任务列表，在全局 `tabs` 中追加对应数量的 `type: 'pending-import'` 页签。
      3. 自动将 `activeTabId` 切换至第一个新增的待配置 Tab，引导用户进入表单填写。

### 3. 待配置技能表单界面 (`type === 'pending-import'`)
采用清晰直观的**单栏全宽流式布局**。

#### A. 模板搜索与填充组件 (Template Loader) —— 常驻表单最顶部
* **UI 展现**：一个横向的配置条，带标签 `「使用已有技能作为模板」`。
* **Combobox 搜索选择框**：
  * 支持输入拼音/英文/中文快速检索个人仓库中所有的已有技能。
  * **自动匹配**：如果系统通过 `GET /library/skills/match-template` 自动匹配到了仓库同名技能，该 Combobox 将默认选中它，并有一行紫色小字提示：*“系统已自动匹配同名技能「{name}」作为模板，您可以直接使用或点击更换。”*
  * **应用逻辑**：选中技能后，点击旁的「应用模板」按钮，二次确认后，将模板技能的 `display_name`、`description` (面向人类的描述)、`tags` (标签) 以及 `readme_md` (README 内容) 一键载入覆盖到当前表单。

#### B. 基础元数据表单
* **技能英文标识 (name)**：只读单行文本框，背景置灰。标注提示：“标识名由 SKILL.md 声明，不可修改”。
* **显示名称 (display_name)**：单行文本输入框（必填）。
* **简短描述 (description)**：多行文本框 `textarea`（必填，限制 1024 字符）。占位符提示：“请输入在技能卡片和社区展示的简短简介（面向普通人类用户）”。
* **标签 (tags)**：多选标签输入组件。

#### C. 说明文档编辑 (README.md)
* **README 编辑区**：全宽 Markdown 编辑器。
  * 提供「编辑 (Write)」与「预览 (Preview)」实时切换 Tab。
  * **默认载入**：若包内原本带有 `README.md`，自动展示；若无，默认加载系统预置的 Markdown 规范结构骨架，引导用户补全。

#### D. 高级配置（折叠面板）
* 折叠展示 `License` (协议) 和 `Compatibility` (兼容性说明) 属性。

#### E. 操作栏
固定悬浮在页面底部：
* **[确认保存并导入]**（高亮紫色/蓝色按钮）：
  1. 调用后端更新 API，将修改后的元数据存入数据库。
  2. 调用写文件 API，将更新后的 README 文本写回物理文件。
  3. 执行成功后，**直接将该 Tab 的 `type` 改为 `'skill'`**，移除紫色圆点，更新对应的 `skillId`，使之变更为正常的技能详情 Tab，并刷新仓库主列表。
* **[放弃导入]**：二次确认后，直接从全局 `tabs` 中关闭并销毁该 Tab。

---

## 三、 后端 API 的手术刀式扩展

为了配合前端元数据确认与提交保存，我们需要合理扩展后端接口：

### 1. 数据库访问层 (`backend/db.py`)
* 在 `UserLibrarySkillsFacade` 中新增元数据修改方法：
  ```python
  def update_meta(
      self,
      library_id: str,
      user_uuid: str,
      *,
      display_name: str | None = None,
      description: str | None = None,
      readme_md: str | None = None,
      tags: str | None = None,
  ) -> bool:
      """更新个人仓库技能的展示元数据。"""
  ```

### 2. API 路由层 (`backend/community/library.py`)
* **获取未导入的运行层技能列表**：
  * `GET /library/skills/unimported`
  * 扫描并返回本地运行层技能目录，排除已被收集至仓库中的同名技能。
* **更新仓库技能元数据**：
  * `PUT /library/skills/{library_id}/meta`
  * 接收前端编辑后的元数据，更新数据库记录。

### 3. 运行层导入 API 扩展 (`POST /library/skills/collect`)
* 扩展 `CollectSkillRequest` 的 Payload：
  ```python
  class CollectSkillRequest(BaseModel):
      skill_name: str = Field(..., min_length=1, max_length=64)
      template_id: str | None = None
      display_name: str | None = None
      description: str | None = None
      readme_md: str | None = None
      tags: str | None = None
  ```
* 后端逻辑在 `collect_skill_to_library` 中，如果 Payload 传入了修改后的字段，则优先使用传入字段作为新建记录的值，若为 `None` 才使用模板继承或 `SKILL.md` 的默认值。
