<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  type UserLibrarySkill,
  type LibrarySkillSort,
  type CommunitySkillSummary,
  listLibrarySkills,
  getLibrarySkill,
  getLibraryPublishForm,
  publishLibrarySkill,
  installLibrarySkill,
  getErrorMessage,
  getCurrentUserId,
  uploadLibrarySkillZip,
  collectLibrarySkill,
  matchLibrarySkillTemplate,
  parseRuntimeSkill,
  updateLibrarySkillMeta,
  deleteLibrarySkill,
  bulkDeleteLibrarySkills,
  forkLibrarySkill,
  listCommunitySkills,
  listLibrarySkillFiles,
  readLibrarySkillFileContent,
  type LibraryFileEntry,
} from '../api'
import { listSkills, validateSkillName } from '../skills'
import { renderMarkdown } from '../markdown/renderer'
import { useProjects } from '../composables/useProjects'
import { useNotification } from '../composables/useNotification'
import { useUserSkills } from '../composables/useUserSkills'
import LibraryUploadDialog from '../components/LibraryUploadDialog.vue'
import SkillEditorPanel from '../components/SkillEditorPanel.vue'
import { useChatSkillSidebar } from '../composables/useChatSkillSidebar'
import { confirmDanger, confirmWarning } from '../composables/useConfirmDialog'

const { projects, loadProjects } = useProjects()
const { showError, showSuccess } = useNotification()
const { skills: userSkills, load: loadUserSkills } = useUserSkills()

// ── 标签页系统 ──────────────────────────────────────────────────────────
interface Tab {
  id: string
  type: 'main' | 'skill' | 'import-console' | 'pending-import' | 'pending-publish'
  label: string
  skillId?: string
  pendingData?: {
    libraryId: string
    name: string
    formName: string
    formDisplayName: string
    formDescription: string
    formReadmeMd: string
    formTags: string[]
    formVersion: string
    source: 'zip' | 'runtime' | 'fork'
    templateMatched?: boolean
    matchedTemplate?: UserLibrarySkill | null
    rawDescription?: string
  }
  publishData?: {
    libraryId: string
    name: string
    displayName: string
    description: string
    readmeMd: string
    originalReadmeMd: string
    tags: string[]
    version: string
    suggestedVersion: string
    changelog: string
    communitySkillId: string | null
    trackedSkill: CommunitySkillSummary | null
    referenceSkill: CommunitySkillSummary | null
  }
  lastAccessed: number
}

const TAB_TTL = 5 * 3600 * 1000 // 5 小时自动清除过期标签页

function loadTabs(): Tab[] {
  try {
    const raw = sessionStorage.getItem('library-tabs')
    if (raw) {
      const parsed: Tab[] = JSON.parse(raw)
      const now = Date.now()
      const valid = parsed.filter(
        (t) => t.type === 'main' || t.type === 'import-console' || now - t.lastAccessed < TAB_TTL
      )
      
      const mainTab = valid.find((t) => t.id === 'main') || {
        id: 'main',
        type: 'main',
        label: '我的仓库',
        lastAccessed: Date.now(),
      }
      const importConsoleTab = valid.find((t) => t.id === 'import-console') || {
        id: 'import-console',
        type: 'import-console',
        label: '导入技能',
        lastAccessed: Date.now(),
      }
      const others = valid.filter((t) => t.id !== 'main' && t.id !== 'import-console')
      return [mainTab, importConsoleTab, ...others]
    }
  } catch { /* ignore */ }
  return [
    { id: 'main', type: 'main', label: '我的仓库', lastAccessed: Date.now() },
    { id: 'import-console', type: 'import-console', label: '导入技能', lastAccessed: Date.now() },
  ]
}
function saveTabs(t: Tab[]): void {
  try {
    sessionStorage.setItem('library-tabs', JSON.stringify(t))
  } catch { /* ignore */ }
}

const tabs = ref<Tab[]>(loadTabs())
const activeTabId = ref(tabs.value[0]?.id ?? 'main')

const activeTab = computed(() => tabs.value.find((t) => t.id === activeTabId.value) ?? tabs.value[0])

const currentPendingData = computed(() => {
  if (activeTab.value && activeTab.value.type === 'pending-import' && activeTab.value.pendingData) {
    return activeTab.value.pendingData
  }
  return null
})

const currentPublishData = computed(() => {
  if (activeTab.value && activeTab.value.type === 'pending-publish' && activeTab.value.publishData) {
    return activeTab.value.publishData
  }
  return null
})



function openTab(tab: Tab): void {
  tab.lastAccessed = Date.now()
  saveTabs(tabs.value)
  activeTabId.value = tab.id
}

function openSkillTab(skill: UserLibrarySkill): void {
  const existing = tabs.value.find((t) => t.type === 'skill' && t.skillId === skill.id)
  if (existing) {
    existing.lastAccessed = Date.now()
    saveTabs(tabs.value)
    activeTabId.value = existing.id
    return
  }
  const label = skill.display_name || skill.name
  const newTab: Tab = {
    id: `skill:${skill.id}`,
    type: 'skill',
    label,
    skillId: skill.id,
    lastAccessed: Date.now(),
  }
  tabs.value.push(newTab)
  saveTabs(tabs.value)
  activeTabId.value = newTab.id
}

function closeTab(tabId: string): void {
  if (tabId === 'main' || tabId === 'import-console') return
  const idx = tabs.value.findIndex((t) => t.id === tabId)
  if (idx === -1) return

  tabs.value.splice(idx, 1)
  saveTabs(tabs.value)

  if (activeTabId.value === tabId) {
    const next = tabs.value[Math.min(idx, tabs.value.length - 1)]
    activeTabId.value = next?.id ?? 'main'
  }
}

// 定时清理过期标签页
let cleanupTimer: ReturnType<typeof setInterval> | null = null

function cleanupExpiredTabs(): void {
  const now = Date.now()
  const before = tabs.value.length
  const removedIds: string[] = []
  
  tabs.value = tabs.value.filter((t) => {
    if (t.type === 'main') return true
    const isExpired = now - t.lastAccessed >= TAB_TTL
    if (isExpired) {
      removedIds.push(t.id)
      return false
    }
    return true
  })

  if (tabs.value.length < before) {
    saveTabs(tabs.value)
    const stillExists = tabs.value.find((t) => t.id === activeTabId.value)
    if (!stillExists) {
      activeTabId.value = 'main'
      detailSkill.value = null
    }
  }
}

// ── 右侧侧边栏及多选/拖拽状态 ────────────────────────────────────────────
const sidebarOpen = ref(localStorage.getItem('library-sidebar-open') !== 'false')

watch(sidebarOpen, (val) => {
  localStorage.setItem('library-sidebar-open', String(val))
})
const userExpanded = ref(true)
const projectExpanded = ref(true)

const selectedSkillIds = ref<string[]>([])
const selectedProjectIds = ref<string[]>([])

// 多选时自动展开侧边栏
watch(selectedSkillIds, (ids) => {
  if (ids.length > 0) sidebarOpen.value = true
})

const projectSkillsMap = ref<Record<string, any[]>>({} )
const expandedProjectPids = ref<Record<string, boolean>>({})
const activeDragPid = ref<string | null>(null)
const installingBatch = ref(false)

const sortedProjects = computed(() => {
  return [...projects.value].sort((a, b) => b.timestamp - a.timestamp)
})

// 展开/收起某个项目的已安装技能
async function toggleProjectSublist(pid: string): Promise<void> {
  expandedProjectPids.value[pid] = !expandedProjectPids.value[pid]
  if (expandedProjectPids.value[pid] && !(pid in projectSkillsMap.value)) {
    try {
      const list = await listSkills({ kind: 'project', pid })
      projectSkillsMap.value[pid] = list
    } catch {
      projectSkillsMap.value[pid] = []
    }
  }
}

// ── 侧边栏技能预览与编辑器集成 ──────────────────────────────────────────
const { editingSkill } = useChatSkillSidebar()

function openSkillEditor(kind: 'user' | 'project', skillMeta: any, pid?: string): void {
  const userId = getCurrentUserId()
  if (kind === 'user' && userId) {
    editingSkill.value = {
      space: { kind: 'user', userId },
      name: skillMeta.name,
      displayName: skillMeta.display_name || skillMeta.name,
    }
  } else if (kind === 'project' && pid) {
    editingSkill.value = {
      space: { kind: 'project', pid },
      name: skillMeta.name,
      displayName: skillMeta.display_name || skillMeta.name,
    }
  }
}

// HTML5 Drag & Drop: 拖拽开始
function onDragStart(e: DragEvent, skill: UserLibrarySkill): void {
  if (e.dataTransfer) {
    e.dataTransfer.setData('text/plain', skill.id)
    e.dataTransfer.effectAllowed = 'copy'
  }
}

// HTML5 Drag & Drop: 放置在项目上
async function onDrop(e: DragEvent, pid: string): Promise<void> {
  activeDragPid.value = null
  e.preventDefault()
  if (!e.dataTransfer) return
  const skillId = e.dataTransfer.getData('text/plain')
  if (!skillId) return

  try {
    const r = await installLibrarySkill(skillId, {
      target: 'project',
      pid: pid,
    })
    const project = projects.value.find((p) => p.pid === pid)
    showSuccess(`已成功将技能拖拽安装到项目 "${project?.projectname ?? pid}"：${r.name}`)
    
    // 强制自动展开项目并重载其技能列表
    expandedProjectPids.value[pid] = true
    const list = await listSkills({ kind: 'project', pid })
    projectSkillsMap.value[pid] = list
  } catch (e) {
    showError('拖拽安装失败', getErrorMessage(e))
  }
}

// 批量安装选中的技能到选中的项目中
async function batchInstall(): Promise<void> {
  if (selectedSkillIds.value.length === 0) {
    showError('请先选择需要安装的技能')
    return
  }
  if (selectedProjectIds.value.length === 0) {
    showError('请先选择要安装到的目标项目')
    return
  }

  installingBatch.value = true
  try {
    let successCount = 0
    for (const skillId of selectedSkillIds.value) {
      for (const pid of selectedProjectIds.value) {
        await installLibrarySkill(skillId, {
          target: 'project',
          pid: pid,
        })
      }
      successCount++
    }
    showSuccess(`已成功将 ${successCount} 个选中的技能安装到选中的 ${selectedProjectIds.value.length} 个项目中`)
    
    // 刷新涉及到的项目的已安装技能列表
    for (const pid of selectedProjectIds.value) {
      try {
        const list = await listSkills({ kind: 'project', pid })
        projectSkillsMap.value[pid] = list
      } catch {
        projectSkillsMap.value[pid] = []
      }
    }
    
    // 重置多选状态
    selectedSkillIds.value = []
    selectedProjectIds.value = []
  } catch (e) {
    showError('批量安装失败', getErrorMessage(e))
  } finally {
    installingBatch.value = false
  }
}

// 批量删除选中的仓库技能
const deletingSkills = ref(false)
async function batchDeleteSkills(): Promise<void> {
  if (selectedSkillIds.value.length === 0) return

  const count = selectedSkillIds.value.length
  const confirmed = await confirmDanger({
    title: '批量删除技能',
    message: `确定删除选中的 ${count} 个技能？此操作不可撤销。`,
    confirmText: '删除',
  })
  if (!confirmed) return

  deletingSkills.value = true
  try {
    const result = await bulkDeleteLibrarySkills(selectedSkillIds.value)
    showSuccess(`已删除 ${result.deleted} 个技能`)
    selectedSkillIds.value = []
    await load()
  } catch (e) {
    showError('批量删除失败', getErrorMessage(e))
  } finally {
    deletingSkills.value = false
  }
}

// ── 列表状态 ────────────────────────────────────────────────────────────
const skills = ref<UserLibrarySkill[]>([])
const total = ref(0)
const loading = ref(false)

// ── 搜索 / 筛选 / 排序 ──────────────────────────────────────────────────
const keyword = ref('')
const selectedTags = ref<string[]>([])
const showTagFilter = ref(false)
const tagInputText = ref('')
const tagInputRef = ref<HTMLInputElement | null>(null)
const sortBy = ref<LibrarySkillSort>('newest')

// ── 分页 ────────────────────────────────────────────────────────────────
const pageSize = 24
const currentPage = ref(1)

// ── 详情状态 ────────────────────────────────────────────────────────────
const detailSkill = ref<UserLibrarySkill | null>(null)
const detailLoading = ref(false)
const detailFiles = ref<LibraryFileEntry[]>([])
const detailFilesLoading = ref(false)
const selectedFileName = ref('SKILL.md')
const selectedFileContent = ref('')
const selectedFileLoading = ref(false)
// 展开的文件夹路径集合
const expandedDirs = ref<Set<string>>(new Set())
// 子目录缓存：path -> entries
const dirCache = ref<Map<string, LibraryFileEntry[]>>(new Map())
const installing = ref(false)
const installingProject = ref(false)
const selectedProjectId = ref('')
const deletingDetailSkill = ref(false)
const openingPublish = ref(false)
const publishingSelected = ref(false)
const isPublishing = ref(false)
const publishReferenceSearchText = ref('')
const publishReferenceResults = ref<CommunitySkillSummary[]>([])
const publishReferenceOpen = ref(false)
const publishReferenceLoading = ref(false)

// ── 上传弹窗 ────────────────────────────────────────────────────────────
const showUploadDialog = ref(false)

// ── 标签解析 ────────────────────────────────────────────────────────────
function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// ── 格式化 ──────────────────────────────────────────────────────────────
function skillTitle(skill: UserLibrarySkill): string {
  return skill.display_name || skill.name
}

function sourceLabel(skill: UserLibrarySkill): string {
  switch (skill.source) {
    case 'community':
      return '来自社区'
    case 'zip':
      return 'ZIP 导入'
    case 'fork':
      return 'Fork 复制'
    case 'runtime':
    default:
      return '运行层导入'
  }
}

function formatBytes(n: number | null | undefined): string {
  if (n == null || n <= 0) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatFullDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

// ── 加载（服务端筛选） ───────────────────────────────────────────────────
async function load(): Promise<void> {
  loading.value = true
  try {
    const r = await listLibrarySkills({
      keyword: keyword.value.trim() || undefined,
      tag: selectedTags.value.length > 0 ? selectedTags.value : undefined,
      sort: sortBy.value,
      limit: pageSize,
      offset: (currentPage.value - 1) * pageSize,
    })
    skills.value = r.skills
    total.value = r.total
  } catch (e) {
    showError('加载仓库失败', getErrorMessage(e))
  } finally {
    loading.value = false
  }
}

// ── 详情加载 ────────────────────────────────────────────────────────────
async function openDetail(id: string): Promise<void> {
  detailLoading.value = true
  detailFiles.value = []
  selectedFileName.value = 'SKILL.md'
  selectedFileContent.value = ''
  expandedDirs.value = new Set()
  dirCache.value = new Map()
  try {
    detailSkill.value = await getLibrarySkill(id)
    await loadRootFiles(id)
    await loadFileContent(id, 'SKILL.md')
  } catch (e) {
    showError('加载详情失败', getErrorMessage(e))
  } finally {
    detailLoading.value = false
  }
}

async function loadRootFiles(libraryId: string): Promise<void> {
  detailFilesLoading.value = true
  try {
    const res = await listLibrarySkillFiles(libraryId, '.')
    // rel_path 格式为 "skill/xxx"，去掉 "skill/" 前缀用于 API 调用
    detailFiles.value = res.entries
      .filter((e) => e.name !== 'README.md')
      .map((e) => ({ ...e, rel_path: e.rel_path.replace(/^skill\//, '') }))
    dirCache.value.set('.', detailFiles.value)
  } catch {
    detailFiles.value = []
  } finally {
    detailFilesLoading.value = false
  }
}

async function loadFileContent(libraryId: string, filePath: string): Promise<void> {
  selectedFileName.value = filePath
  selectedFileLoading.value = true
  try {
    const res = await readLibrarySkillFileContent(libraryId, filePath)
    selectedFileContent.value = res.content
  } catch {
    selectedFileContent.value = ''
  } finally {
    selectedFileLoading.value = false
  }
}

/** 排序：文件在前，文件夹在后 */
function sortEntries(entries: LibraryFileEntry[]): LibraryFileEntry[] {
  const files = entries.filter((e) => !e.is_dir)
  const dirs = entries.filter((e) => e.is_dir)
  return [...files, ...dirs]
}

async function toggleDir(dir: LibraryFileEntry): Promise<void> {
  if (!detailSkill.value) return
  const id = detailSkill.value.id

  if (expandedDirs.value.has(dir.rel_path)) {
    // 收起：移除该目录及其所有子目录的展开状态和缓存
    const newExpanded = new Set(expandedDirs.value)
    const newCache = new Map(dirCache.value)
    for (const key of newExpanded) {
      if (key === dir.rel_path || key.startsWith(dir.rel_path + '/')) {
        newExpanded.delete(key)
      }
    }
    for (const key of newCache.keys()) {
      if (key === dir.rel_path || key.startsWith(dir.rel_path + '/')) {
        newCache.delete(key)
      }
    }
    expandedDirs.value = newExpanded
    dirCache.value = newCache
  } else {
    // 展开：加载子目录内容
    try {
      const res = await listLibrarySkillFiles(id, dir.rel_path)
      const entries = sortEntries(
        res.entries.map((e) => ({ ...e, rel_path: e.rel_path.replace(/^skill\//, '') }))
      )
      const newCache = new Map(dirCache.value)
      newCache.set(dir.rel_path, entries)
      dirCache.value = newCache
      const newExpanded = new Set(expandedDirs.value)
      newExpanded.add(dir.rel_path)
      expandedDirs.value = newExpanded
    } catch {
      // 静默失败
    }
  }
}

/** 递归渲染文件树 */
interface FileTreeNode {
  entry: LibraryFileEntry
  depth: number
}

const fileTree = computed<FileTreeNode[]>(() => {
  const result: FileTreeNode[] = []
  function walk(entries: LibraryFileEntry[], depth: number) {
    for (const entry of entries) {
      result.push({ entry, depth })
      if (entry.is_dir && expandedDirs.value.has(entry.rel_path)) {
        const children = dirCache.value.get(entry.rel_path)
        if (children) walk(children, depth + 1)
      }
    }
  }
  walk(sortEntries(detailFiles.value), 0)
  return result
})

// ── 安装 ────────────────────────────────────────────────────────────────
async function doInstall(): Promise<void> {
  if (!detailSkill.value) return
  installing.value = true
  try {
    const r = await installLibrarySkill(detailSkill.value.id, { target: 'user' })
    showSuccess(`已安装到我的技能：${r.name}`)
    void loadUserSkills() // 重新加载用户技能
  } catch (e) {
    showError('安装失败', getErrorMessage(e))
  } finally {
    installing.value = false
  }
}

async function doInstallProject(): Promise<void> {
  if (!detailSkill.value || !selectedProjectId.value) return
  installingProject.value = true
  try {
    const r = await installLibrarySkill(detailSkill.value.id, {
      target: 'project',
      pid: selectedProjectId.value,
    })
    const project = projects.value.find((p) => p.pid === selectedProjectId.value)
    showSuccess(`已安装到项目 ${project?.projectname ?? selectedProjectId.value}：${r.name}`)
    
    // 更新此项目的列表
    const pid = selectedProjectId.value
    expandedProjectPids.value[pid] = true
    const list = await listSkills({ kind: 'project', pid })
    projectSkillsMap.value[pid] = list
  } catch (e) {
    showError('安装失败', getErrorMessage(e))
  } finally {
    installingProject.value = false
  }
}

// ── 删除单个仓库技能 ─────────────────────────────────────────────────────
async function doDeleteDetailSkill(): Promise<void> {
  if (!detailSkill.value) return
  const skill = detailSkill.value
  const confirmed = await confirmDanger({
    title: '删除仓库技能',
    message: `确定删除仓库中的 "${skillTitle(skill)}" 吗？此操作不可撤销。`,
    confirmText: '删除',
  })
  if (!confirmed) return

  deletingDetailSkill.value = true
  try {
    await deleteLibrarySkill(skill.id)
    showSuccess(`已删除 "${skillTitle(skill)}"`)
    selectedSkillIds.value = selectedSkillIds.value.filter((id) => id !== skill.id)
    closeTab(`skill:${skill.id}`)
    detailSkill.value = null
    await load()
  } catch (e) {
    showError('删除技能失败', getErrorMessage(e))
  } finally {
    deletingDetailSkill.value = false
  }
}

// ── Fork ────────────────────────────────────────────────────────────────
function doFork(): void {
  if (!detailSkill.value) return
  const skill = detailSkill.value
  const newTabId = `pending-import:fork:${skill.id}:${Date.now()}`

  const originalDisplayName = skill.display_name || skill.name
  const baseName = originalDisplayName.replace(/ \(自定义版本.*\)$/, '')
  const now = new Date()
  const yy = String(now.getFullYear()).slice(-2)
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  const newDisplayName = `${baseName} (自定义版本 ${yy}${mm}${dd})`

  const newTab: Tab = {
    id: newTabId,
    type: 'pending-import',
    label: `复制：${skill.name}`,
    pendingData: {
      libraryId: skill.id, // 记录源 skill ID，保存时调 fork API
      name: skill.name,
      formName: skill.name,
      formDisplayName: newDisplayName,
      formDescription: skill.description || '',
      formReadmeMd: skill.readme_md || '',
      formTags: parseTags(skill.tags),
      formVersion: skill.version || '1.0.0',
      source: 'fork',
      templateMatched: true,
      matchedTemplate: null,
    },
    lastAccessed: Date.now(),
  }

  tabs.value.push(newTab)
  saveTabs(tabs.value)
  activeTabId.value = newTabId
}

// ── 发布到社区 ──────────────────────────────────────────────────────────
function buildPublishData(form: Awaited<ReturnType<typeof getLibraryPublishForm>>): NonNullable<Tab['publishData']> {
  const skill = form.library_skill
  const tracked = form.community_skill
  return {
    libraryId: skill.id,
    name: skill.name,
    displayName: skill.display_name || skill.name,
    description: skill.description || '',
    readmeMd: skill.readme_md || '',
    originalReadmeMd: skill.readme_md || '',
    tags: parseTags(skill.tags),
    version: form.suggested_version || skill.version || '1.0.0',
    suggestedVersion: form.suggested_version || '1.0.0',
    changelog: '',
    communitySkillId: tracked?.id ?? null,
    trackedSkill: tracked,
    referenceSkill: tracked,
  }
}

async function openPublishTab(libraryId: string, activate = true): Promise<string | null> {
  const existing = tabs.value.find((t) => t.type === 'pending-publish' && t.publishData?.libraryId === libraryId)
  if (existing) {
    if (activate) activeTabId.value = existing.id
    return existing.id
  }

  openingPublish.value = true
  try {
    const form = await getLibraryPublishForm(libraryId)
    const publishData = buildPublishData(form)
    const newTabId = `pending-publish:${libraryId}:${Date.now()}`
    const newTab: Tab = {
      id: newTabId,
      type: 'pending-publish',
      label: `发布：${publishData.displayName || publishData.name}`,
      publishData,
      lastAccessed: Date.now(),
    }
    tabs.value.push(newTab)
    saveTabs(tabs.value)
    if (activate) activeTabId.value = newTabId
    return newTabId
  } catch (e) {
    showError('加载发布表单失败', getErrorMessage(e))
    return null
  } finally {
    openingPublish.value = false
  }
}

async function openPublishForDetail(): Promise<void> {
  if (!detailSkill.value) return
  await openPublishTab(detailSkill.value.id)
}

async function batchOpenPublishTabs(): Promise<void> {
  if (selectedSkillIds.value.length === 0) return
  publishingSelected.value = true
  try {
    let firstTabId: string | null = null
    for (const skillId of selectedSkillIds.value) {
      const tabId = await openPublishTab(skillId, false)
      if (!firstTabId) firstTabId = tabId
    }
    if (firstTabId) {
      activeTabId.value = firstTabId
      showSuccess(`已创建 ${selectedSkillIds.value.length} 个社区发布表单`)
    }
  } finally {
    publishingSelected.value = false
  }
}

async function searchPublishReferences(): Promise<void> {
  const data = currentPublishData.value
  if (!data) return
  publishReferenceLoading.value = true
  publishReferenceOpen.value = true
  try {
    const keywordText = publishReferenceSearchText.value.trim() || data.name
    const res = await listCommunitySkills({ keyword: keywordText, limit: 8, offset: 0, sort: 'popular' })
    publishReferenceResults.value = res.skills
  } catch (e) {
    showError('搜索社区技能失败', getErrorMessage(e))
  } finally {
    publishReferenceLoading.value = false
  }
}

function selectPublishReference(skill: CommunitySkillSummary | null, tab: Tab): void {
  if (!tab.publishData) return
  tab.publishData.referenceSkill = skill
  publishReferenceOpen.value = false
  publishReferenceSearchText.value = ''
  saveTabs(tabs.value)
}

function removePublishTag(tag: string, tab: Tab): void {
  if (!tab.publishData) return
  tab.publishData.tags = tab.publishData.tags.filter((t) => t !== tag)
  saveTabs(tabs.value)
}

function addPublishTag(tab: Tab): void {
  if (!tab.publishData) return
  const t = tagText.value.trim()
  if (t && !tab.publishData.tags.includes(t)) {
    tab.publishData.tags.push(t)
    saveTabs(tabs.value)
  }
  tagText.value = ''
}

async function submitPublish(tab: Tab): Promise<void> {
  if (!tab.publishData) return
  const data = tab.publishData
  if (!data.name.trim()) {
    showError('技能标识名不能为空')
    return
  }
  const nameError = validateSkillName(data.name.trim())
  if (nameError) {
    showError(nameError)
    return
  }
  if (!data.displayName.trim()) {
    showError('显示名称不能为空')
    return
  }
  if (!data.description.trim()) {
    showError('简短描述不能为空')
    return
  }
  if (!/^[0-9]+\.[0-9]+\.[0-9]+$/.test(data.version.trim())) {
    showError('版本号格式必须为 X.Y.Z，例如 1.0.0')
    return
  }
  if (!data.changelog.trim()) {
    showError('请填写本次发布的变更说明')
    return
  }

  isPublishing.value = true
  try {
    const updated = await updateLibrarySkillMeta(data.libraryId, {
      name: data.name.trim(),
      display_name: data.displayName.trim(),
      description: data.description.trim(),
      readme_md: data.readmeMd,
      tags: JSON.stringify(data.tags),
    })
    await publishLibrarySkill(data.libraryId, {
      version: data.version.trim(),
      changelog: data.changelog.trim(),
    })
    showSuccess('已提交到社区 Owner 审核')
    closeTab(tab.id)
    await load()
    openSkillTab(updated)
  } catch (e) {
    showError('发布到社区失败', getErrorMessage(e))
  } finally {
    isPublishing.value = false
  }
}

async function cancelPublish(tabId: string): Promise<void> {
  const confirmed = await confirmWarning({
    title: '放弃社区发布',
    message: '是否确定放弃本次社区发布表单？已填写内容不会提交。',
    confirmText: '放弃',
  })
  if (confirmed) {
    closeTab(tabId)
  }
}

// ── 标签筛选操作 ────────────────────────────────────────────────────────
function toggleTagFilter(): void {
  showTagFilter.value = !showTagFilter.value
  if (showTagFilter.value) {
    setTimeout(() => tagInputRef.value?.focus(), 50)
  }
}

function addTag(tag: string): void {
  const t = tag.trim()
  if (t && !selectedTags.value.includes(t)) {
    selectedTags.value.push(t)
    currentPage.value = 1
    void load()
  }
  tagInputText.value = ''
}

// ── 移除标签 ────────────────────────────────────────────────────────────
function removeTag(tag: string): void {
  selectedTags.value = selectedTags.value.filter((t) => t !== tag)
  currentPage.value = 1
  void load()
}

function handleTagInputKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter') {
    e.preventDefault()
    addTag(tagInputText.value)
  }
}

function changeSort(next: LibrarySkillSort): void {
  if (sortBy.value === next) return
  sortBy.value = next
  currentPage.value = 1
  void load()
}

// ── 分页 ────────────────────────────────────────────────────────────────
function gotoPage(page: number): void {
  currentPage.value = Math.max(1, Math.min(totalPages.value, page))
  void load()
}

const pageNumbers = computed(() => {
  const pages: number[] = []
  const tp = totalPages.value
  const cur = currentPage.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 3) pages.push(-1)
    for (let i = Math.max(2, cur - 1); i <= Math.min(tp - 1, cur + 1); i++) pages.push(i)
    if (cur < tp - 2) pages.push(-1)
    pages.push(tp)
  }
  return pages
})

// ── 生命周期 ────────────────────────────────────────────────────────────
onMounted(() => {
  editingSkill.value = null
  document.title = '我的仓库 · Learnova'
  void load()
  void loadProjects()
  void loadUserSkills()
  void loadImportSourceSkills()
  cleanupExpiredTabs()
  cleanupTimer = setInterval(cleanupExpiredTabs, 10 * 60 * 1000)
})

onBeforeUnmount(() => {
  if (cleanupTimer) {
    clearInterval(cleanupTimer)
    cleanupTimer = null
  }
  editingSkill.value = null
})

// ── 导入与上传队列系统 ──────────────────────────────────────────────────
interface ImportQueueItem {
  id: string
  name: string
  source: 'zip' | 'runtime'
  file?: File
  size?: number
  status: 'pending' | 'parsing' | 'success' | 'failed'
  error?: string
  parsedData?: {
    libraryId?: string
    name: string
    displayName: string
    readmeMd: string
    description: string
  }
}

const importQueue = ref<ImportQueueItem[]>([])
const runtimeSelectedSkillNames = ref<string[]>([])

function toggleRuntimeSkillSelection(name: string): void {
  const index = runtimeSelectedSkillNames.value.indexOf(name)
  if (index > -1) {
    runtimeSelectedSkillNames.value.splice(index, 1)
  } else {
    runtimeSelectedSkillNames.value.push(name)
  }
}

const isUploading = ref(false)

const importSourceType = ref('user')
const importSourceSkills = ref<any[]>([])
const loadingSourceSkills = ref(false)

async function loadImportSourceSkills(): Promise<void> {
  loadingSourceSkills.value = true
  try {
    if (importSourceType.value === 'user') {
      const userId = getCurrentUserId()
      if (userId) {
        importSourceSkills.value = await listSkills({ kind: 'user', userId })
      } else {
        importSourceSkills.value = []
      }
    } else {
      const pid = importSourceType.value
      importSourceSkills.value = await listSkills({ kind: 'project', pid })
    }
  } catch (e) {
    showError('加载本地技能失败', getErrorMessage(e))
    importSourceSkills.value = []
  } finally {
    loadingSourceSkills.value = false
  }
}

watch(importSourceType, () => {
  void loadImportSourceSkills()
})

function handleZipDrop(e: DragEvent): void {
  e.preventDefault()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    addZipsToQueue(files)
  }
}

function handleZipSelect(e: Event): void {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    addZipsToQueue(target.files)
  }
}

function addZipsToQueue(files: FileList): void {
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    if (!file.name.endsWith('.zip')) {
      showError(`文件 "${file.name}" 不是 ZIP 压缩包`)
      continue
    }
    if (file.size > 40 * 1024 * 1024) {
      showError(`文件 "${file.name}" 超过 40MB 限制`)
      continue
    }
    const id = `zip-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`
    importQueue.value.push({
      id,
      name: file.name,
      source: 'zip',
      file,
      size: file.size,
      status: 'pending',
    })
  }
  // 自动开始解析
  void processQueue()
}

function addRuntimeSkillsToQueue(): void {
  for (const name of runtimeSelectedSkillNames.value) {
    const exists = importQueue.value.some((q) => q.source === 'runtime' && q.name === name)
    if (exists) continue

    importQueue.value.push({
      id: `rt-${name}-${Date.now()}`,
      name,
      source: 'runtime',
      status: 'pending',
    })
  }
  runtimeSelectedSkillNames.value = []
  // 自动开始解析
  void processQueue()
}

function removeFromQueue(idx: number): void {
  importQueue.value.splice(idx, 1)
}

async function processQueue(): Promise<void> {
  if (isUploading.value) return
  isUploading.value = true

  try {
    for (const item of importQueue.value) {
      if (item.status !== 'pending') continue
      item.status = 'parsing'

      try {
        if (item.source === 'zip' && item.file) {
          const res = await uploadLibrarySkillZip(item.file)
          item.status = 'success'
          item.parsedData = {
            libraryId: res.id,
            name: res.name,
            displayName: res.display_name || res.name,
            readmeMd: res.readme_md || '',
            description: res.description || '',
          }
        } else if (item.source === 'runtime') {
          const res = await parseRuntimeSkill(item.name)
          item.status = 'success'
          item.parsedData = {
            name: res.frontmatter.name,
            displayName: res.frontmatter.display_name || res.frontmatter.name,
            readmeMd: res.readme_md || '',
            description: res.frontmatter.description || '',
          }
        }
      } catch (err) {
        item.status = 'failed'
        item.error = getErrorMessage(err)
      }
    }
  } finally {
    isUploading.value = false
  }
}

function startQueueImport(): void {
  const successes = importQueue.value.filter((q) => q.status === 'success' && q.parsedData)
  if (successes.length === 0) {
    showError('队列中没有解析成功的技能包')
    return
  }

  let firstNewTabId = ''
  for (const item of successes) {
    const data = item.parsedData!
    const newTabId = `pending-import:${data.name}:${Date.now()}-${Math.random().toString(36).substr(2, 5)}`
    if (!firstNewTabId) firstNewTabId = newTabId

    const newTab: Tab = {
      id: newTabId,
      type: 'pending-import',
      label: data.name,
      pendingData: {
        libraryId: data.libraryId || '',
        name: data.name,
        formName: data.name,
        formDisplayName: data.displayName || data.name,
        formDescription: data.description || '',
        formReadmeMd: data.readmeMd || '',
        formTags: [],
        formVersion: '1.0.0',
        source: item.source,
        templateMatched: false,
        matchedTemplate: null,
        rawDescription: data.description || '',
      },
      lastAccessed: Date.now(),
    }
    tabs.value.push(newTab)
  }

  saveTabs(tabs.value)
  // 清空队列
  importQueue.value = []
  
  if (firstNewTabId) {
    activeTabId.value = firstNewTabId
  }
}

// ── 待导入表单状态与模板应用 ──────────────────────────────────────────────
const tagText = ref('')
const formTemplateSearchText = ref('')
const formTemplateSearchOpen = ref(false)
const isSavingPending = ref(false)

const filteredTemplates = computed(() => {
  const kw = formTemplateSearchText.value.toLowerCase().trim()
  if (!kw) return skills.value.slice(0, 10)
  return skills.value.filter(
    (s) =>
      s.name.toLowerCase().includes(kw) ||
      (s.display_name && s.display_name.toLowerCase().includes(kw))
  )
})

async function fetchMatchedTemplate(skillName: string, tab: Tab): Promise<void> {
  if (!tab.pendingData) return
  try {
    const res = await matchLibrarySkillTemplate(skillName)
    tab.pendingData.matchedTemplate = res.matched
    if (res.matched) {
      applyTemplateToTab(res.matched, tab)
    }
  } catch {
    tab.pendingData.matchedTemplate = null
  }
}

function applyTemplateToTab(tmpl: UserLibrarySkill | null, tab: Tab): void {
  if (!tmpl || !tab.pendingData) return
  tab.pendingData.formDisplayName = tmpl.display_name || tmpl.name
  tab.pendingData.formDescription = tmpl.description || ''
  tab.pendingData.formReadmeMd = tmpl.readme_md || ''
  if (tmpl.version) {
    tab.pendingData.formVersion = tmpl.version
  }
  
  if (tmpl.tags) {
    try {
      const parsed = JSON.parse(tmpl.tags)
      tab.pendingData.formTags = Array.isArray(parsed) ? parsed : []
    } catch {
      tab.pendingData.formTags = []
    }
  } else {
    tab.pendingData.formTags = []
  }
  tab.pendingData.matchedTemplate = tmpl
  saveTabs(tabs.value)
  showSuccess(`已成功为「${tab.pendingData.name}」应用模板「${tmpl.display_name || tmpl.name}」`)
}

function addFormTag(tag: string, tab: Tab): void {
  const t = tag.trim()
  if (t && tab.pendingData && !tab.pendingData.formTags.includes(t)) {
    tab.pendingData.formTags.push(t)
    saveTabs(tabs.value)
  }
  tagText.value = ''
}

function removeFormTag(tag: string, tab: Tab): void {
  if (tab.pendingData) {
    tab.pendingData.formTags = tab.pendingData.formTags.filter((t) => t !== tag)
    saveTabs(tabs.value)
  }
}

async function savePendingImport(tab: Tab): Promise<void> {
  if (!tab.pendingData) return
  const data = tab.pendingData
  if (!data.formName.trim()) {
    showError('技能标识名不能为空')
    return
  }
  const nameError = validateSkillName(data.formName.trim())
  if (nameError) {
    showError(nameError)
    return
  }
  if (!data.formDisplayName.trim()) {
    showError('显示名称不能为空')
    return
  }
  if (!data.formDescription.trim()) {
    showError('简短描述不能为空')
    return
  }

  isSavingPending.value = true
  try {
    const tagsJson = JSON.stringify(data.formTags)
    let finalSkillId = ''

    if (data.source === 'fork') {
      const res = await forkLibrarySkill(data.libraryId, {
        name: data.formName,
        display_name: data.formDisplayName,
        description: data.formDescription,
        readme_md: data.formReadmeMd,
        tags: tagsJson,
      })
      finalSkillId = res.id
    } else if (data.source === 'runtime') {
      const res = await collectLibrarySkill({
        skill_name: data.name,
        name: data.formName,
        display_name: data.formDisplayName,
        description: data.formDescription,
        readme_md: data.formReadmeMd,
        tags: tagsJson,
      })
      finalSkillId = res.id
    } else {
      const libId = data.libraryId
      const res = await updateLibrarySkillMeta(libId, {
        name: data.formName,
        display_name: data.formDisplayName,
        description: data.formDescription,
        readme_md: data.formReadmeMd,
        tags: tagsJson,
      })
      finalSkillId = res.id
    }

    showSuccess(`技能 "${data.formDisplayName}" 导入并配置成功`)
    
    tab.type = 'skill'
    tab.skillId = finalSkillId
    tab.label = data.formDisplayName || data.formName
    tab.id = `skill:${finalSkillId}`
    saveTabs(tabs.value)
    
    activeTabId.value = tab.id
    void load()
    void loadUserSkills()
  } catch (err) {
    showError('导入技能保存失败', getErrorMessage(err))
  } finally {
    isSavingPending.value = false
  }
}

async function cancelPendingImport(tabId: string): Promise<void> {
  const confirmed = await confirmWarning({
    title: '放弃导入技能包',
    message: '是否确定放弃导入该技能包？配置将不会被保存。',
    confirmText: '放弃',
  })
  if (confirmed) {
    closeTab(tabId)
  }
}

// 关键词变化时回到第一页并重新加载
watch(keyword, () => {
  if (activeTabId.value !== 'main') {
    activeTabId.value = 'main'
  }
  currentPage.value = 1
  void load()
})

// 监听标签页切换
watch(activeTabId, async (newId) => {
  const tab = tabs.value.find((t) => t.id === newId)
  if (tab) {
    tab.lastAccessed = Date.now()
    saveTabs(tabs.value)
  }
  if (tab?.type === 'skill' && tab.skillId) {
    detailSkill.value = null
    selectedProjectId.value = ''
    await openDetail(tab.skillId)
  } else if (tab?.type === 'pending-import' && tab.pendingData) {
    const pData = currentPendingData.value
    if (pData && !pData.templateMatched) {
      pData.templateMatched = true
      saveTabs(tabs.value)
      await fetchMatchedTemplate(pData.name, tab)
    }
  }
})
</script>

<template>
  <div class="flex h-full w-full overflow-hidden bg-[#f3f4f6] relative">
    <!-- 右上角固定切换按钮组 -->
    <div class="fixed top-3 right-4 z-50 flex items-center gap-1.5">
      <!-- 关闭技能编辑按钮（仅处于编辑状态时显示） -->
      <button
        v-if="editingSkill"
        class="flex h-8 w-8 items-center justify-center rounded-full border border-[#d1d5db] bg-white text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95 shadow-sm"
        type="button"
        title="关闭编辑"
        @click="editingSkill = null"
      >
        <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
          <path d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      <button
        class="flex h-8 w-8 items-center justify-center rounded-full border border-[#d1d5db] bg-white text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95 shadow-sm"
        type="button"
        :title="sidebarOpen ? '收起技能面板' : '展开技能面板'"
        @click="sidebarOpen = !sidebarOpen"
      >
        <svg
          class="h-4 w-4 transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
          :class="sidebarOpen ? 'rotate-180' : 'rotate-0'"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          viewBox="0 0 24 24"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
    </div>

    <!-- 左侧主面板 -->
    <div class="flex flex-1 min-w-0 flex-col overflow-hidden relative">
      <!-- 技能内联编辑器 / 仓库内容切换 -->
      <Transition name="skill-editor" mode="out-in">
        <SkillEditorPanel
          v-if="editingSkill"
          :key="editingSkill.space.kind === 'user' ? ('user-' + editingSkill.space.userId + '-' + editingSkill.name) : ('project-' + editingSkill.space.pid + '-' + editingSkill.name)"
          :space="editingSkill.space"
          :skill-name="editingSkill.name"
          :display-name="editingSkill.displayName"
          @close="editingSkill = null"
        />
        <div v-else key="library-content" class="absolute inset-0 flex flex-col min-h-0">
      <!-- ═══ 顶栏：居中搜索框 + 操作 ═══ -->
      <div class="relative flex h-14 flex-shrink-0 items-center justify-between bg-transparent px-6">
        <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3">
          <div
            class="relative flex items-center bg-[#e5e7eb]/70 hover:bg-[#e5e7eb] focus-within:bg-white focus-within:ring-2 focus-within:ring-[#9ca3af]/20 transition-all rounded-2xl w-72 h-8"
          >
            <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
              <svg class="h-4 w-4 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <input
              v-model="keyword"
              class="block w-full rounded-2xl bg-transparent py-1 pl-9 pr-3 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none"
              placeholder="搜索仓库技能..."
              type="search"
            />
          </div>
        </div>


      </div>

      <!-- ═══ 标签栏 (浏览器风格) ═══ -->
      <div class="flex flex-shrink-0 items-end gap-0.5 bg-transparent px-6 overflow-x-auto no-scrollbar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="group relative flex items-center gap-1 whitespace-nowrap rounded-t-lg px-2.5 py-1 !text-[13px] leading-none font-normal transition-colors duration-200 font-hans"
          :class="tab.id === activeTabId
            ? 'bg-white text-[#1f2937]'
            : 'bg-transparent text-[#6b7280] hover:text-[#1f2937] hover:bg-[#e5e7eb]/60'"
          @click="openTab(tab)"
        >
          <span
            v-if="tab.type === 'main' || tab.type === 'import-console'"
            class="mr-1 h-1.5 w-1.5 rounded-full bg-[#9ca3af] flex-shrink-0"
            title="常驻页面"
          ></span>
          <span
            v-else-if="tab.type === 'pending-import'"
            class="mr-1 h-1.5 w-1.5 rounded-full bg-purple-500 flex-shrink-0"
            title="待配置导入"
          ></span>
          <span
            v-else-if="tab.type === 'pending-publish'"
            class="mr-1 h-1.5 w-1.5 rounded-full bg-emerald-500 flex-shrink-0"
            title="待发布到社区"
          ></span>
          <span class="max-w-[160px] truncate">{{ tab.label }}</span>
          <span
            v-if="tab.type !== 'main' && tab.type !== 'import-console'"
            class="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full text-[#9ca3af] hover:bg-[#e5e7eb] hover:text-[#1f2937] transition-colors flex-shrink-0"
            @click.stop="closeTab(tab.id)"
          >
            <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </span>
        </button>
      </div>

      <!-- ═══ 标签内容区 ═══ -->
      <div class="min-h-0 flex-1 flex flex-col overflow-hidden">
        <!-- ── 主界面标签页：技能列表 ── -->
        <template v-if="activeTab.type === 'main'">
          <!-- ═══ 筛选栏 ═══ -->
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <!-- 排序 -->
            <select
              class="h-7 !text-xs font-hans border-0 border-b-2 border-[#e5e7eb] hover:border-[#1f2937] rounded-none bg-transparent pl-0 pr-3 text-[#4b5563] outline-none cursor-pointer appearance-none"
              :value="sortBy"
              @change="changeSort(($event.target as HTMLSelectElement).value as LibrarySkillSort)"
              style="background-image: url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2210%22 height=%226%22 fill=%22none%22%3E%3Cpath stroke=%22%236b7280%22 stroke-linecap=%22round%22 stroke-linejoin=%22round%22 stroke-width=%221.5%22 d=%22M1 1l4 4 4-4%22/%3E%3C/svg%3E'); background-repeat: no-repeat; background-position: right 0 center;"
            >
              <option value="newest">最新</option>
              <option value="oldest">最早</option>
              <option value="name-asc">名称 A-Z</option>
              <option value="name-desc">名称 Z-A</option>
            </select>

            <!-- 标签筛选 -->
            <button
              type="button"
              class="flex items-center gap-1 h-7 !text-xs font-hans border-0 border-b-2 rounded-none pl-0 pr-2 transition-colors"
              :class="showTagFilter || selectedTags.length > 0 ? 'border-[#1f2937] text-[#1f2937]' : 'border-[#e5e7eb] text-[#6b7280] hover:border-[#1f2937] hover:text-[#1f2937]'"
              @click="toggleTagFilter"
            >
              <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              <span>标签</span>
            </button>

            <!-- 已选标签 chips -->
            <template v-for="tag in selectedTags" :key="tag">
              <span class="inline-flex items-center gap-1 bg-[#e5e7eb] rounded-sm px-2 py-0.5 !text-xs font-hans text-[#4b5563]">
                {{ tag }}
                <button type="button" class="text-[#9ca3af] hover:text-[#1f2937]" @click="removeTag(tag)">
                  <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            </template>

            <!-- 标签输入 -->
            <div v-if="showTagFilter" class="flex items-center">
              <input
                ref="tagInputRef"
                v-model="tagInputText"
                class="w-28 h-7 !text-xs font-hans border-0 border-b-2 border-[#e5e7eb] focus:border-[#1f2937] rounded-none bg-transparent pl-0 pr-2 text-[#4b5563] placeholder:text-[#9ca3af] outline-none"
                placeholder="输入标签回车"
                @keydown="handleTagInputKeydown"
              />
            </div>

            <div class="flex-1" />

            <!-- 多选时：已选数量 + 删除按钮 -->
            <template v-if="selectedSkillIds.length > 0">
              <span class="text-xs text-[#6b7280] font-hans">已选 {{ selectedSkillIds.length }} 个</span>
              <button
                type="button"
                :disabled="publishingSelected"
                @click="batchOpenPublishTabs"
                class="!text-xs text-emerald-600 hover:text-emerald-700 hover:underline font-hans disabled:opacity-40"
              >
                {{ publishingSelected ? '准备中...' : '上传到社区' }}
              </button>
              <button
                type="button"
                :disabled="deletingSkills"
                @click="batchDeleteSkills"
                class="!text-xs text-red-500 hover:text-red-700 hover:underline font-hans disabled:opacity-40"
              >
                {{ deletingSkills ? '删除中...' : '删除' }}
              </button>
              <button
                type="button"
                @click="selectedSkillIds = []"
                class="!text-xs text-[#6b7280] hover:text-[#1f2937] hover:underline font-hans"
              >
                取消选择
              </button>
            </template>

            <span class="text-xs text-[#9ca3af] font-hans">共 {{ total }} 个技能</span>
          </div>

          <!-- ═══ 卡片网格 ═══ -->
          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <div v-if="loading" class="py-16 text-center text-sm text-[#9ca3af]">加载中...</div>

            <div v-else-if="skills.length === 0" class="py-16 text-center text-sm text-[#9ca3af]">
              仓库中还没有技能，从技能管理页收集或从社区安装吧。
            </div>

            <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              <button
                v-for="s in skills"
                :key="s.id"
                draggable="true"
                @dragstart="onDragStart($event, s)"
                class="flex w-full flex-col gap-3 rounded-xl bg-white p-5 text-left shadow-sm transition hover:bg-[#f9fafb] hover:shadow-md active:scale-[0.99] relative group cursor-grab"
                type="button"
                @click="openSkillTab(s)"
              >
                <!-- 标题行 -->
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center gap-2 min-w-0">
                    <!-- 批量选择 Checkbox -->
                    <input
                      type="checkbox"
                      :value="s.id"
                      v-model="selectedSkillIds"
                      @click.stop
                      class="h-[18px] w-[18px] flex-shrink-0 rounded text-[#1f2937] focus:ring-[#1f2937]/20 border-gray-300 cursor-pointer"
                    />
                    <span class="truncate text-sm font-semibold text-[#1f2937]">{{ skillTitle(s) }}</span>
                  </div>
                  <span
                    class="flex flex-shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] whitespace-nowrap"
                    :class="s.source === 'community' ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
                  >
                    {{ sourceLabel(s) }}
                  </span>
                </div>

                <!-- 描述 -->
                <p class="line-clamp-2 text-xs text-[#6b7280] leading-relaxed">
                  {{ s.description || '无描述' }}
                </p>

                <!-- 底部：标签 + 版本 + 大小 -->
                <div class="mt-auto flex items-center justify-between gap-2">
                  <div class="flex items-center gap-1.5 min-w-0 overflow-hidden">
                    <template v-for="tag in parseTags(s.tags).slice(0, 2)" :key="tag">
                      <span class="rounded-sm bg-[#f3f4f6] px-1.5 py-0.5 text-[11px] text-[#9ca3af] truncate max-w-[80px]">
                        {{ tag }}
                      </span>
                    </template>
                  </div>
                  <div class="flex flex-shrink-0 items-center gap-1.5 text-[11px] text-[#9ca3af] tabular-nums">
                    <span>{{ formatBytes(s.size_bytes) }}</span>
                  </div>
                </div>
              </button>
            </div>

            <!-- 分页 -->
            <div v-if="totalPages > 1" class="mt-5 mb-4 flex items-center justify-center gap-1.5">
              <button
                class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.97] disabled:opacity-40"
                :disabled="currentPage === 1"
                type="button"
                @click="gotoPage(currentPage - 1)"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <template v-for="p in pageNumbers" :key="p">
                <span v-if="p === -1" class="px-1 text-xs text-[#9ca3af]">...</span>
                <button
                  v-else
                  class="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition-all duration-200 active:scale-[0.97]"
                  :class="p === currentPage ? 'bg-[#1f2937] text-white' : 'text-[#6b7280] hover:bg-[#e5e7eb]'"
                  type="button"
                  @click="gotoPage(p)"
                >
                  {{ p }}
                </button>
              </template>
              <button
                class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.97] disabled:opacity-40"
                :disabled="currentPage === totalPages"
                type="button"
                @click="gotoPage(currentPage + 1)"
              >
                <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </template>

        <!-- ── 导入控制台标签页 ── -->
        <template v-else-if="activeTab.type === 'import-console'">
          <!-- 顶部栏 -->
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <span class="!text-xs font-semibold text-[#1f2937]">导入技能包到个人仓库</span>
            <span class="!text-xs text-[#9ca3af]">将运行层技能或外部 ZIP 包导入仓库，支持模板填充</span>
          </div>
          <!-- 内容 -->
          <div class="min-h-0 flex-1 flex flex-col overflow-y-auto px-6 py-6 font-hans">

            <!-- 来源选择卡片 -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
              <!-- ZIP 压缩包上传 -->
              <div 
                @dragover.prevent
                @drop="handleZipDrop"
                class="flex flex-col items-center justify-center border-2 border-dashed border-[#d1d5db] rounded-none bg-white p-5 min-h-[260px] h-full transition-all hover:border-[#1f2937] hover:bg-gray-50/50 group relative cursor-pointer"
              >
                <input 
                  type="file" 
                  accept=".zip" 
                  multiple 
                  class="absolute inset-0 opacity-0 cursor-pointer" 
                  @change="handleZipSelect"
                />
                <span class="text-sm font-medium text-[#1f2937]">点击选择或将 ZIP 拖拽到这里</span>
                <span class="text-xs text-[#9ca3af] mt-1">支持多选，大小不超过 40MB</span>
              </div>

              <!-- 本地运行层导入 -->
              <div class="flex flex-col rounded-none border border-[#e5e7eb] bg-white p-5 shadow-sm min-h-[260px] h-full">
                <h3 class="text-sm font-medium text-[#1f2937] mb-0.5">从本地运行层导入</h3>
                <p class="text-xs text-[#9ca3af] mb-2.5">选择本地正在运行的技能进行配置导入，作为新版本或独立副本。</p>
                
                <!-- 1. 来源选择 -->
                <div class="mb-2">
                  <label class="block text-[11px] font-semibold text-[#4b5563] mb-0.5">技能来源（用户/项目）：</label>
                  <select
                    v-model="importSourceType"
                    class="block w-full rounded-xl border border-[#d1d5db] bg-transparent px-3 py-2 text-sm text-[#1f2937] outline-none focus:ring-1 focus:ring-[#1f2937]"
                  >
                    <option value="user">当前用户运行层技能 (全局)</option>
                    <option
                      v-for="p in projects"
                      :key="p.pid"
                      :value="p.pid"
                    >
                      项目：{{ p.projectname }}
                    </option>
                  </select>
                </div>

                <!-- 2. 技能多选 -->
                <div>
                  <label class="block text-[11px] font-semibold text-[#4b5563] mb-0.5">选择技能：</label>
                  <div class="flex gap-2">
                    <div class="relative flex-1 min-w-0">
                      <div v-if="loadingSourceSkills" class="text-xs text-[#9ca3af] py-4 text-center">
                        正在载入本地技能...
                      </div>
                      <div
                        v-else
                        class="block w-full rounded-xl border border-[#d1d5db] bg-[#f9fafb] p-1 overflow-y-auto max-h-[160px] min-h-[110px] space-y-1"
                      >
                        <div
                          v-for="s in importSourceSkills"
                          :key="s.name"
                          @click="toggleRuntimeSkillSelection(s.name)"
                          :class="[
                            'flex items-center gap-2 px-3 py-2 text-xs rounded-lg cursor-pointer transition select-none border',
                            runtimeSelectedSkillNames.includes(s.name)
                              ? 'bg-purple-50 text-purple-700 border-purple-300 font-medium shadow-sm'
                              : 'bg-white text-[#1f2937] border-[#e5e7eb] hover:bg-gray-50'
                          ]"
                        >
                          <input
                            type="checkbox"
                            :checked="runtimeSelectedSkillNames.includes(s.name)"
                            @click.stop
                            @change="toggleRuntimeSkillSelection(s.name)"
                            class="h-4 w-4 rounded border-[#d1d5db] text-purple-600 focus:ring-purple-500 focus:ring-offset-0"
                          />
                          <span class="flex-1 truncate font-medium text-[13px]">
                            {{ s.display_name || s.name }}
                          </span>
                          <span :class="[
                            'text-[10px] font-mono opacity-80',
                            runtimeSelectedSkillNames.includes(s.name) ? 'text-purple-400' : 'text-gray-500'
                          ]">
                            {{ s.name }}
                          </span>
                        </div>
                      </div>
                      <div v-if="!loadingSourceSkills && importSourceSkills.length === 0" class="text-[10px] text-red-500 mt-1">
                        ⚠️ 选中的项目空间下无本地技能
                      </div>
                    </div>
                    <button
                      type="button"
                      :disabled="runtimeSelectedSkillNames.length === 0 || loadingSourceSkills"
                      @click="addRuntimeSkillsToQueue"
                      class="h-auto self-stretch rounded-xl bg-[#1f2937] px-6 text-sm font-semibold text-white transition hover:bg-[#111827] active:scale-95 disabled:opacity-40 disabled:scale-100 flex-shrink-0"
                    >
                      添加
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="importQueue.length > 0" class="flex-1 min-h-0 flex flex-col bg-white rounded-2xl border border-[#e5e7eb] p-5 shadow-sm mt-6">
              <div class="flex items-center justify-between mb-4 flex-shrink-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-semibold text-[#1f2937]">待导入队列</span>
                  <span class="text-[10px] bg-purple-50 text-purple-600 px-2 py-0.5 rounded-full font-medium">
                    {{ importQueue.length }} 个项目
                  </span>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    @click="importQueue = []"
                    :disabled="isUploading"
                    class="h-9 px-4 rounded-xl border border-gray-200 text-sm font-semibold text-gray-500 hover:bg-gray-50 transition active:scale-95 disabled:opacity-40"
                  >
                    清空全部
                  </button>
                  <button
                    type="button"
                    @click="startQueueImport"
                    :disabled="isUploading || !importQueue.some(q => q.status === 'success')"
                    class="h-9 px-5 rounded-xl bg-purple-600 text-sm font-semibold text-white transition hover:bg-purple-700 active:scale-95 disabled:opacity-40 shadow-sm shadow-purple-100 flex items-center gap-1.5"
                  >
                    <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                    <span>开始配置导入</span>
                  </button>
                </div>
              </div>

              <!-- 队列列表 -->
              <div class="flex-1 overflow-y-auto space-y-2 pr-1 min-h-[150px]">
                <div
                  v-for="(item, idx) in importQueue"
                  :key="item.id"
                  class="flex items-center justify-between p-3 rounded-xl border border-gray-100 bg-gray-50/50 hover:bg-gray-50 transition"
                >
                  <div class="flex items-center gap-2.5 min-w-0">
                    <span
                      class="h-2 w-2 rounded-full"
                      :class="{
                        'bg-gray-300': item.status === 'pending',
                        'bg-purple-500 animate-pulse': item.status === 'parsing',
                        'bg-green-500': item.status === 'success',
                        'bg-red-500': item.status === 'failed'
                      }"
                    ></span>
                    <div class="min-w-0">
                      <div class="text-xs font-medium text-gray-700 truncate" :title="item.name">
                        {{ item.name }}
                      </div>
                      <div class="flex items-center gap-2 mt-0.5 text-[10px] text-gray-400">
                        <span>{{ item.source === 'zip' ? 'ZIP 包' : '本地运行层' }}</span>
                        <span v-if="item.size">• {{ (item.size / 1024).toFixed(1) }} KB</span>
                      </div>
                    </div>
                  </div>

                  <div class="flex items-center gap-3">
                    <span
                      class="text-[10px] font-medium"
                      :class="{
                        'text-gray-400': item.status === 'pending',
                        'text-purple-600': item.status === 'parsing',
                        'text-green-600': item.status === 'success',
                        'text-red-500': item.status === 'failed'
                      }"
                    >
                      <span v-if="item.status === 'pending'">等待解析</span>
                      <span v-else-if="item.status === 'parsing'">正在解析...</span>
                      <span v-else-if="item.status === 'success'">解析成功</span>
                      <span v-else-if="item.status === 'failed'" :title="item.error">
                        解析失败: {{ item.error }}
                      </span>
                    </span>

                    <button
                      v-if="item.status !== 'parsing'"
                      type="button"
                      @click="removeFromQueue(idx)"
                      class="text-gray-400 hover:text-red-500 transition p-1 rounded-lg hover:bg-gray-100"
                    >
                      <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </template>

        <!-- ── 待配置技能表单标签页 ── -->
        <template v-else-if="activeTab.type === 'pending-import' && currentPendingData">
          <!-- 顶部栏：标题 + 来源 + 放弃按钮 -->
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <span class="h-2 w-2 rounded-full bg-purple-500 animate-pulse"></span>
            <span class="!text-xs font-semibold text-[#1f2937]">配置技能：{{ currentPendingData.name }}</span>
            <span class="!text-xs text-[#9ca3af]">
              {{ currentPendingData.source === 'zip' ? 'ZIP 包上传' : '运行层导入' }}
            </span>
            <div class="flex-1"></div>
            <button
              type="button"
              @click="cancelPendingImport(activeTab.id)"
              class="!text-xs text-red-500 hover:text-red-700 hover:underline"
            >
              放弃导入
            </button>
          </div>
          <!-- 表单内容 -->
          <div class="relative flex-1 min-h-0 flex flex-col">
            <div class="min-h-0 flex-1 flex flex-col overflow-y-auto px-6 py-6 font-hans pb-24">

            <!-- 1. 模板填充栏 (Template Loader) -->
            <div class="mb-5 rounded-none border border-purple-100 bg-purple-50/20 p-4">
              <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div class="min-w-0">
                  <span class="text-xs font-semibold text-purple-900 block">应用已有技能作为配置模板</span>
                  <span v-if="currentPendingData.matchedTemplate" class="text-[11px] text-purple-600 block mt-0.5">
                    💡 已为您自动匹配并应用同名模板「{{ currentPendingData.matchedTemplate.display_name || currentPendingData.matchedTemplate.name }}」的数据。
                  </span>
                  <span v-else class="text-[11px] text-[#9ca3af] block mt-0.5">
                    未发现同名模板。您可以选择下拉框中的其他技能来填充。
                  </span>
                </div>

                <!-- 模板可搜索下拉选择器 -->
                <div class="flex items-center gap-2 flex-shrink-0 relative">
                  <div class="relative w-56">
                    <input
                      v-model="formTemplateSearchText"
                      @focus="formTemplateSearchOpen = true"
                      class="block w-full rounded-none border border-purple-200 bg-white py-1.5 pl-3 pr-8 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-purple-500"
                      placeholder="搜索并选择模板技能..."
                    />
                    <button
                      type="button"
                      @click="formTemplateSearchOpen = !formTemplateSearchOpen"
                      class="absolute inset-y-0 right-0 flex items-center pr-2.5 text-gray-400"
                    >
                      <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <!-- 下拉选择面板 -->
                    <div
                      v-if="formTemplateSearchOpen"
                      class="absolute right-0 top-full z-50 mt-1 max-h-56 w-full overflow-y-auto rounded-none border border-gray-200 bg-white py-1 shadow-lg"
                    >
                      <div
                        v-if="filteredTemplates.length === 0"
                        class="px-3 py-2 text-xs text-[#9ca3af] text-center"
                      >
                        未找到模板
                      </div>
                      <button
                        v-for="tmpl in filteredTemplates"
                        :key="tmpl.id"
                        type="button"
                        @click="applyTemplateToTab(tmpl, activeTab); formTemplateSearchOpen = false; formTemplateSearchText = ''"
                        class="block w-full px-3 py-1.5 text-left text-xs text-[#374151] hover:bg-purple-50 hover:text-purple-700 transition"
                      >
                        {{ tmpl.display_name || tmpl.name }} ({{ tmpl.name }})
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 2. 表单字段 - 单栏流式布局 -->
            <div class="space-y-6 w-full">
              <!-- name (可编辑) -->
              <div>
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">技能标识名 (name) <span class="text-red-500">*</span></label>
                <input
                  v-model="currentPendingData.formName"
                  type="text"
                  placeholder="支持中文、字母、数字、下划线和中划线"
                  class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                />
                <span class="text-[10px] text-[#9ca3af] block mt-1">技能的唯一标识，将作为后端物理文件中的 SKILL.md name 配置项。</span>
              </div>

              <!-- display_name -->
              <div>
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">显示名称 (display_name) <span class="text-red-500">*</span></label>
                <input
                  v-model="currentPendingData.formDisplayName"
                  type="text"
                  placeholder="如：中文翻译助手"
                  class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                />
              </div>

              <!-- description -->
              <div>
                <div class="flex items-center justify-between mb-1.5">
                  <label class="block text-xs font-semibold text-[#4b5563]">简短描述 (description) <span class="text-red-500">*</span></label>
                  <button
                    v-if="currentPendingData.rawDescription"
                    type="button"
                    @click="currentPendingData.formDescription = currentPendingData.rawDescription"
                    class="text-[10px] text-purple-600 hover:text-purple-700 hover:underline select-none cursor-pointer"
                    title="从原技能 SKILL.md 导入描述"
                  >
                    复制原技能描述
                  </button>
                </div>
                <textarea
                  v-model="currentPendingData.formDescription"
                  rows="3"
                  placeholder="面向人类用户的一句话简介，将显示在仓库卡片和社区列表中。不超过 1024 字符。"
                  class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                ></textarea>
              </div>

              <!-- tags -->
              <div>
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">标签 (tags)</label>
                <div class="flex flex-wrap items-center gap-1.5 p-2 rounded-none border border-[#e5e7eb] bg-white min-h-[38px] w-full">
                  <span 
                    v-for="t in currentPendingData.formTags" 
                    :key="t"
                    class="inline-flex items-center gap-1 bg-purple-50 text-purple-700 px-2 py-0.5 rounded text-xs"
                  >
                    {{ t }}
                    <button type="button" @click="removeFormTag(t, activeTab)" class="text-purple-400 hover:text-purple-700 font-bold font-sans">×</button>
                  </span>
                  <input
                    v-model="tagText"
                    placeholder="输入标签并回车添加"
                    @keydown.enter.prevent="addFormTag(tagText, activeTab)"
                    class="flex-1 min-w-[120px] bg-transparent border-0 outline-none text-xs py-0.5 text-[#1f2937] placeholder:text-[#9ca3af]"
                  />
                </div>
              </div>

              <!-- README.md Markdown 编辑器 -->
              <div>
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">详细说明文档 (README.md)</label>
                <div class="rounded-none border border-[#e5e7eb] bg-white overflow-hidden flex flex-col">
                  <!-- 编辑器控制条 -->
                  <div class="flex bg-gray-50 border-b border-[#e5e7eb] px-3 py-1.5 justify-between items-center flex-shrink-0">
                    <span class="text-[11px] font-semibold text-[#6b7280]">Markdown 编辑</span>
                    <span class="text-[10px] text-[#9ca3af]">支持标准 Markdown 语法</span>
                  </div>
                  <!-- 编辑区 -->
                  <textarea
                    v-model="currentPendingData.formReadmeMd"
                    rows="8"
                    placeholder="请输入关于此技能的使用方法、AI 代理调用建议等详细文档..."
                    class="block w-full border-0 bg-transparent px-4 py-3 text-xs text-[#374151] font-mono leading-relaxed outline-none resize-y min-h-[160px]"
                  ></textarea>
                </div>
              </div>
            </div>

            </div>
            <!-- 悬浮动作条 -->
            <div class="absolute bottom-6 right-6 flex items-center gap-3 z-30">
              <button
                type="button"
                :disabled="isSavingPending"
                @click="cancelPendingImport(activeTab.id)"
                class="h-9 rounded-xl border border-[#d1d5db] bg-white px-5 text-xs font-medium text-[#4b5563] transition hover:bg-[#f9fafb] active:scale-95 disabled:opacity-40"
              >
                放弃导入
              </button>
              <button
                type="button"
                :disabled="isSavingPending"
                @click="savePendingImport(activeTab)"
                class="h-9 rounded-xl bg-purple-600 px-6 text-xs font-medium text-white transition hover:bg-purple-700 active:scale-95 disabled:opacity-40 disabled:scale-100 flex items-center gap-1.5 shadow-sm shadow-purple-200"
              >
                <svg v-if="isSavingPending" class="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                确认保存并导入到仓库
              </button>
            </div>
          </div>
        </template>

        <!-- ── 待发布到社区表单标签页 ── -->
        <template v-else-if="activeTab.type === 'pending-publish' && currentPublishData">
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <span class="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span class="!text-xs font-semibold text-[#1f2937]">发布到社区：{{ currentPublishData.displayName || currentPublishData.name }}</span>
            <span class="!text-xs text-[#9ca3af]">
              {{ currentPublishData.trackedSkill ? '发布为已追踪社区技能的新版本' : '发布为新的社区技能' }}
            </span>
            <div class="flex-1"></div>
            <button
              type="button"
              @click="cancelPublish(activeTab.id)"
              class="!text-xs text-red-500 hover:text-red-700 hover:underline"
            >
              放弃发布
            </button>
          </div>

          <div class="relative flex-1 min-h-0 flex flex-col">
            <div class="min-h-0 flex-1 overflow-y-auto px-6 py-6 pb-24 font-hans">
              <div class="mb-5 rounded-none border border-emerald-100 bg-emerald-50/30 p-4">
                <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div class="min-w-0 space-y-2">
                    <span class="text-xs font-semibold text-emerald-900 block">社区追踪</span>
                    <div class="grid grid-cols-[76px_1fr] gap-x-3 gap-y-1 text-xs">
                      <span class="text-[#9ca3af]">当前追踪</span>
                      <span class="text-[#1f2937]">
                        <template v-if="currentPublishData.trackedSkill">
                          {{ currentPublishData.trackedSkill.display_name || currentPublishData.trackedSkill.name }}
                        </template>
                        <template v-else>
                          无追踪，提交后将新建社区技能
                        </template>
                      </span>
                      <span class="text-[#9ca3af]">版本 ID</span>
                      <span class="truncate font-mono text-[11px] text-[#4b5563]">{{ currentPublishData.libraryId }}</span>
                      <span class="text-[#9ca3af]">版本建议</span>
                      <span class="text-[#1f2937]">v{{ currentPublishData.suggestedVersion }}</span>
                    </div>
                    <p class="text-[11px] leading-relaxed text-[#9ca3af]">
                      当前仓库技能 ID 会作为社区版本 ID；同一仓库条目重复提交不会代表新的版本变动。需要真正发布新版本时，请先复制/Fork 生成新的仓库条目。
                    </p>
                  </div>

                  <div class="w-full flex-shrink-0 lg:w-[300px]">
                    <span class="mb-1.5 block text-[11px] font-semibold text-[#4b5563]">参考社区技能</span>
                    <div class="relative flex gap-2">
                      <input
                        v-model="publishReferenceSearchText"
                        class="h-8 min-w-0 flex-1 rounded-none border border-emerald-200 bg-white px-3 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-emerald-600"
                        placeholder="搜索社区技能作对照"
                        @keydown.enter.prevent="searchPublishReferences"
                      />
                      <button
                        type="button"
                        :disabled="publishReferenceLoading"
                        @click="searchPublishReferences"
                        class="h-8 rounded-xl bg-emerald-600 px-3 text-xs font-medium text-white transition hover:bg-emerald-700 active:scale-95 disabled:opacity-40"
                      >
                        搜索
                      </button>
                      <div
                        v-if="publishReferenceOpen"
                        class="absolute right-0 top-full z-50 mt-1 max-h-64 w-full overflow-y-auto rounded-none border border-[#e5e7eb] bg-white py-1 shadow-lg"
                      >
                        <button
                          type="button"
                          class="block w-full px-3 py-1.5 text-left text-xs text-[#6b7280] hover:bg-emerald-50 hover:text-emerald-700"
                          @click="selectPublishReference(null, activeTab)"
                        >
                          不选择参考技能
                        </button>
                        <div v-if="publishReferenceLoading" class="px-3 py-2 text-center text-xs text-[#9ca3af]">搜索中...</div>
                        <div v-else-if="publishReferenceResults.length === 0" class="px-3 py-2 text-center text-xs text-[#9ca3af]">未找到社区技能</div>
                        <template v-else>
                          <button
                            v-for="skill in publishReferenceResults"
                            :key="skill.id"
                            type="button"
                            class="block w-full px-3 py-1.5 text-left text-xs text-[#374151] hover:bg-emerald-50 hover:text-emerald-700"
                            @click="selectPublishReference(skill, activeTab)"
                          >
                            <span class="block truncate">{{ skill.display_name || skill.name }}</span>
                            <span class="block truncate text-[10px] text-[#9ca3af]">{{ skill.name }}</span>
                          </button>
                        </template>
                      </div>
                    </div>
                    <p class="mt-1 text-[10px] text-[#9ca3af]">
                      参考选择只用于填写时对照，不会改变后端发布追踪。
                    </p>
                    <p v-if="currentPublishData.referenceSkill" class="mt-2 rounded-lg bg-white px-3 py-2 text-[11px] text-[#4b5563]">
                      正在参考：{{ currentPublishData.referenceSkill.display_name || currentPublishData.referenceSkill.name }}
                    </p>
                  </div>
                </div>
              </div>

              <div class="space-y-6 w-full">
                <div>
                  <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">技能标识名 (name) <span class="text-red-500">*</span></label>
                  <input
                    v-model="currentPublishData.name"
                    type="text"
                    placeholder="支持中文、字母、数字、下划线和中划线"
                    class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                  />
                </div>

                <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
                  <div>
                    <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">发布版本号 (version) <span class="text-red-500">*</span></label>
                    <input
                      v-model="currentPublishData.version"
                      type="text"
                      placeholder="格式如：1.0.0"
                      class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                    />
                    <span class="text-[10px] text-[#9ca3af] block mt-1">请使用三位版本号规范；建议值来自最新已审核版本末位 +1。</span>
                  </div>

                  <div>
                    <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">显示名称 (display_name) <span class="text-red-500">*</span></label>
                    <input
                      v-model="currentPublishData.displayName"
                      type="text"
                      placeholder="如：中文翻译助手"
                      class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                    />
                  </div>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">简短描述 (description) <span class="text-red-500">*</span></label>
                  <textarea
                    v-model="currentPublishData.description"
                    rows="3"
                    placeholder="面向社区用户的一句话简介，将显示在社区列表中。"
                    class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                  ></textarea>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">本次变更说明 (changelog) <span class="text-red-500">*</span></label>
                  <textarea
                    v-model="currentPublishData.changelog"
                    rows="3"
                    placeholder="说明这次发布新增、修正或调整了什么。"
                    class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                  ></textarea>
                </div>

                <div>
                  <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">标签 (tags)</label>
                  <div class="flex flex-wrap items-center gap-1.5 p-2 rounded-none border border-[#e5e7eb] bg-white min-h-[38px] w-full">
                    <span
                      v-for="t in currentPublishData.tags"
                      :key="t"
                      class="inline-flex items-center gap-1 bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded text-xs"
                    >
                      {{ t }}
                      <button type="button" @click="removePublishTag(t, activeTab)" class="text-emerald-400 hover:text-emerald-700 font-bold font-sans">×</button>
                    </span>
                    <input
                      v-model="tagText"
                      placeholder="输入标签并回车添加"
                      @keydown.enter.prevent="addPublishTag(activeTab)"
                      class="flex-1 min-w-[120px] bg-transparent border-0 outline-none text-xs py-0.5 text-[#1f2937] placeholder:text-[#9ca3af]"
                    />
                  </div>
                </div>

                <div>
                  <div class="mb-1.5 flex items-center gap-2">
                    <label class="block text-xs font-semibold text-[#4b5563]">详细说明文档 (README.md)</label>
                    <span
                      v-if="currentPublishData.readmeMd !== currentPublishData.originalReadmeMd"
                      class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700"
                    >
                      README 已修改，提交前会同步到仓库
                    </span>
                  </div>
                  <div class="rounded-none border border-[#e5e7eb] bg-white overflow-hidden flex flex-col">
                    <div class="flex bg-gray-50 border-b border-[#e5e7eb] px-3 py-1.5 justify-between items-center flex-shrink-0">
                      <span class="text-[11px] font-semibold text-[#6b7280]">Markdown 编辑</span>
                      <span class="text-[10px] text-[#9ca3af]">支持标准 Markdown 语法</span>
                    </div>
                    <textarea
                      v-model="currentPublishData.readmeMd"
                      rows="10"
                      placeholder="请输入关于此技能的使用方法、AI 代理调用建议等详细文档..."
                      class="block w-full border-0 bg-transparent px-4 py-3 text-xs text-[#374151] font-mono leading-relaxed outline-none resize-y min-h-[220px]"
                    ></textarea>
                  </div>
                </div>
              </div>
            </div>

            <div class="absolute bottom-6 right-6 flex items-center gap-3 z-30">
              <button
                type="button"
                :disabled="isPublishing"
                @click="cancelPublish(activeTab.id)"
                class="h-9 rounded-xl border border-[#d1d5db] bg-white px-5 text-xs font-medium text-[#4b5563] transition hover:bg-[#f9fafb] active:scale-95 disabled:opacity-40"
              >
                放弃发布
              </button>
              <button
                type="button"
                :disabled="isPublishing"
                @click="submitPublish(activeTab)"
                class="h-9 rounded-xl bg-emerald-600 px-6 text-xs font-medium text-white transition hover:bg-emerald-700 active:scale-95 disabled:opacity-40 disabled:scale-100 flex items-center gap-1.5 shadow-sm shadow-emerald-200"
              >
                <svg v-if="isPublishing" class="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                提交发布审核
              </button>
            </div>
          </div>
        </template>
        
        <!-- ── 技能详情标签页 ── -->
        <template v-else-if="activeTab.type === 'skill'">
          <!-- 顶部栏 -->
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <span class="!text-xs font-semibold text-[#1f2937]">{{ detailSkill ? skillTitle(detailSkill) : '加载中...' }}</span>
            <span
              v-if="detailSkill"
              class="rounded-full px-2 py-0.5 !text-xs whitespace-nowrap"
              :class="detailSkill.source === 'community' ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
            >
              {{ sourceLabel(detailSkill) }}
            </span>
            <div class="flex-1"></div>
            <button
              v-if="detailSkill"
              type="button"
              :disabled="openingPublish"
              @click="openPublishForDetail"
              class="!text-xs text-emerald-600 hover:text-emerald-700 hover:underline disabled:opacity-40"
            >
              {{ openingPublish ? '准备中...' : '上传到社区' }}
            </button>
            <button
              v-if="detailSkill"
              type="button"
              :disabled="deletingDetailSkill"
              @click="doDeleteDetailSkill"
              class="!text-xs text-red-500 hover:text-red-700 hover:underline disabled:opacity-40"
            >
              {{ deletingDetailSkill ? '删除中...' : '删除技能' }}
            </button>
          </div>
          <!-- 内容 -->
          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <!-- 加载态 -->
            <div v-if="detailLoading" class="flex h-full items-center justify-center text-sm text-[#9ca3af]">
              加载中...
            </div>

            <template v-else-if="detailSkill">
              <div class="flex flex-col lg:flex-row gap-4">
                <!-- 左侧/主体：描述与 README -->
                <div class="flex-1 min-w-0 w-full flex flex-col gap-4">
                  <div v-if="detailSkill.description">
                    <span class="inline-block rounded-md bg-[#1f2937] px-2 py-0.5 text-[11px] font-semibold text-white mb-2">Description</span>
                    <p class="text-sm text-[#374151] leading-relaxed">{{ detailSkill.description }}</p>
                  </div>
                  <div v-if="detailSkill.description && detailSkill.readme_md" class="border-t border-[#e5e7eb]"></div>
                  <div v-if="detailSkill.readme_md" class="flex-1">
                    <span class="inline-block rounded-md bg-[#1f2937] px-2 py-0.5 text-[11px] font-semibold text-white mb-2">README.md</span>
                    <div class="markdown-body" v-html="renderMarkdown(detailSkill.readme_md)"></div>
                  </div>
                  <div v-if="!detailSkill.description && !detailSkill.readme_md" class="py-12 text-center text-sm text-[#9ca3af]">
                    暂无描述和 README 内容
                  </div>

                  <!-- 选中文件内容 -->
                  <div v-if="selectedFileName" class="border-t border-[#e5e7eb] pt-4">
                    <span class="inline-block rounded-md bg-[#1f2937] px-2 py-0.5 text-[11px] font-semibold text-white mb-2">{{ selectedFileName.split('/').pop() }}</span>
                    <div v-if="selectedFileLoading" class="text-xs text-[#9ca3af] py-4">加载中…</div>
                    <pre v-else-if="selectedFileContent" class="whitespace-pre-wrap font-sans text-sm text-[#374151] leading-relaxed bg-[#f9fafb] rounded-lg p-4 overflow-x-auto">{{ selectedFileContent }}</pre>
                    <div v-else class="text-xs text-[#9ca3af] py-4">无法读取文件内容</div>
                  </div>

                </div>

                <!-- 右侧：属性详情与操作 -->
                <div class="w-full lg:w-[320px] flex-shrink-0 flex flex-col gap-4">
                  <!-- 属性详情 -->
                  <div class="bg-white rounded-xl border border-[#e5e7eb] p-5">
                    <h3 class="text-sm font-semibold text-[#1f2937] mb-3">技能属性</h3>
                    <div class="grid grid-cols-[70px_1fr] gap-y-2.5 text-xs">
                      <span class="text-[#9ca3af]">名称</span>
                      <span class="text-[#1f2937] font-medium truncate">{{ detailSkill.name }}</span>
                      <span class="text-[#9ca3af]">显示名</span>
                      <span class="text-[#1f2937] truncate">{{ detailSkill.display_name || '-' }}</span>
                      <span class="text-[#9ca3af]">版本</span>
                      <span class="text-[#1f2937]">v{{ detailSkill.version }}</span>
                      <span class="text-[#9ca3af]">大小</span>
                      <span class="text-[#1f2937]">{{ formatBytes(detailSkill.size_bytes) }}</span>
                      <span class="text-[#9ca3af]">来源</span>
                      <span class="text-[#1f2937]">{{ sourceLabel(detailSkill) }}</span>
                      <span class="text-[#9ca3af]">创建时间</span>
                      <span class="text-[#1f2937]">{{ formatFullDate(detailSkill.created_at) }}</span>
                      <span class="text-[#9ca3af]">更新时间</span>
                      <span class="text-[#1f2937]">{{ formatFullDate(detailSkill.updated_at) }}</span>
                      <template v-if="detailSkill.changelog">
                        <span class="text-[#9ca3af]">变更</span>
                        <span class="text-[#1f2937] whitespace-pre-wrap">{{ detailSkill.changelog }}</span>
                      </template>
                      <span class="text-[#9ca3af]">标签</span>
                      <div class="flex flex-wrap gap-1">
                        <template v-if="parseTags(detailSkill.tags).length > 0">
                          <span
                            v-for="tag in parseTags(detailSkill.tags)"
                            :key="tag"
                            class="rounded-sm bg-[#f3f4f6] px-1.5 py-0.5 text-[10px] text-[#6b7280]"
                          >{{ tag }}</span>
                        </template>
                        <span v-else class="text-[#9ca3af]">-</span>
                      </div>
                    </div>
                  </div>

                  <!-- 操作区 -->
                  <div class="bg-white rounded-xl border border-[#e5e7eb] p-5 flex flex-col gap-3">
                    <button
                      class="w-full rounded-xl bg-emerald-600 py-2.5 text-sm text-white font-semibold transition-all duration-200 hover:bg-emerald-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                      type="button"
                      :disabled="openingPublish"
                      @click="openPublishForDetail"
                    >
                      {{ openingPublish ? '准备发布...' : '上传到社区' }}
                    </button>

                    <button
                      class="w-full rounded-xl bg-[#f3f4f6] py-2.5 text-sm text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98]"
                      type="button"
                      @click="doFork"
                    >
                      复制（Fork）
                    </button>

                    <div class="h-px bg-[#e5e7eb]" />

                    <div class="flex flex-col gap-2">
                      <span class="text-xs font-medium text-[#4b5563]">安装到特定项目</span>
                      <div class="flex gap-2">
                        <select
                          v-model="selectedProjectId"
                          class="h-9 flex-1 rounded-xl bg-white px-3 text-sm text-[#374151] outline-none shadow-sm focus:ring-2 focus:ring-[#1f2937]/20 border border-[#e5e7eb]"
                        >
                          <option value="">选择项目</option>
                          <option v-for="project in projects" :key="project.pid" :value="project.pid">
                            {{ project.projectname }}
                          </option>
                        </select>
                        <button
                          class="h-9 rounded-xl bg-[#f3f4f6] px-4 text-xs text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 border border-[#e5e7eb]"
                          :disabled="installingProject || !selectedProjectId"
                          type="button"
                          @click="doInstallProject"
                        >
                          安装
                        </button>
                      </div>
                    </div>

                    <div class="flex gap-2 mt-1">
                      <button
                        class="flex-1 h-9 rounded-xl bg-[#1f2937] text-xs text-white font-semibold transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                        :disabled="installing"
                        type="button"
                        @click="doInstall"
                      >
                        {{ installing ? '安装中...' : '安装到用户级' }}
                      </button>

                      <button
                        class="h-9 rounded-xl bg-red-600 text-xs text-white font-semibold transition-all duration-200 hover:bg-red-700 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 px-3"
                        :disabled="deletingDetailSkill"
                        type="button"
                        @click="doDeleteDetailSkill"
                      >
                      {{ deletingDetailSkill ? '删除中...' : '删除技能' }}
	                    </button>
	                  </div>
	                </div>

	                  <!-- 文件结构 -->
	                  <div class="bg-white rounded-xl border border-[#e5e7eb] p-5">
                    <h3 class="text-sm font-semibold text-[#1f2937] mb-3">文件结构</h3>
                    <div v-if="detailFilesLoading" class="text-xs text-[#9ca3af] py-2">加载中…</div>
                    <div v-else-if="fileTree.length === 0" class="text-xs text-[#9ca3af] py-2">暂无文件</div>
                    <div v-else class="flex flex-col gap-0.5">
                      <template v-for="node in fileTree" :key="node.entry.rel_path">
                        <!-- 文件夹 -->
                        <button
                          v-if="node.entry.is_dir"
                          class="flex items-center gap-1.5 text-xs py-0.5 text-left w-full rounded px-1 transition-colors text-[#374151] hover:bg-[#f3f4f6] cursor-pointer"
                          :style="{ paddingLeft: `${node.depth * 16 + 4}px` }"
                          type="button"
                          @click="toggleDir(node.entry)"
                        >
                          <span class="text-[10px] w-3 text-center">{{ expandedDirs.has(node.entry.rel_path) ? '▼' : '▶' }}</span>
                          <span>📁</span>
                          <span class="truncate font-medium">{{ node.entry.name }}</span>
                        </button>
                        <!-- 文件 -->
                        <button
                          v-else
                          class="flex items-center gap-1.5 text-xs py-0.5 text-left w-full rounded px-1 transition-colors"
                          :style="{ paddingLeft: `${node.depth * 16 + 4}px` }"
                          :class="selectedFileName === node.entry.rel_path
                            ? 'bg-[#e5e7eb] text-[#1f2937]'
                            : 'text-[#374151] hover:bg-[#f3f4f6] cursor-pointer'"
                          type="button"
                          @click="loadFileContent(detailSkill!.id, node.entry.rel_path)"
                        >
                          <span class="w-3"></span>
                          <span>📄</span>
                          <span class="truncate">{{ node.entry.name }}</span>
                          <span class="ml-auto text-[10px] text-[#9ca3af]">{{ formatBytes(node.entry.size) }}</span>
                        </button>
                      </template>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </template>

        <!-- ── 方便后续扩展其他标签页类型 ── -->
        <!-- <template v-else-if="activeTab.type === 'some_future_type'"> -->
        <!-- </template> -->
      </div>

      <!-- ═══ 上传弹窗 ═══ -->
      <LibraryUploadDialog
        v-if="showUploadDialog"
        @close="showUploadDialog = false"
        @done="showUploadDialog = false; load()"
      />
      </div>
      </Transition>
    </div>

    <!-- 右侧技能与项目管理侧边栏 -->
    <aside
      :class="[
        'flex flex-shrink-0 flex-col bg-white border-l border-[#e5e7eb] transition-all duration-300 overflow-hidden font-hans',
        sidebarOpen ? 'w-56' : 'w-0'
      ]"
    >
      <div class="flex h-full w-56 flex-shrink-0 flex-col overflow-hidden">
        <!-- 侧边栏标题栏 -->
        <div class="flex h-14 flex-shrink-0 items-center justify-between px-4 border-b border-[#e5e7eb]">
          <span class="text-sm font-semibold text-[#1f2937]">
            {{ selectedSkillIds.length > 0 ? `已选 ${selectedSkillIds.length} 个` : '技能与项目' }}
          </span>
          <button
            v-if="selectedSkillIds.length > 0"
            type="button"
            class="text-[11px] text-[#6b7280] hover:text-[#1f2937] transition-colors"
            @click="selectedSkillIds = []"
          >
            清除
          </button>
        </div>

        <!-- 侧边栏滚动列表 -->
        <div class="flex-1 overflow-y-auto px-3 py-4 space-y-4">

          <!-- 多选模式：已选技能列表 + 批量操作 -->
          <template v-if="selectedSkillIds.length > 0">
            <div class="space-y-1">
              <div
                v-for="sid in selectedSkillIds"
                :key="sid"
                class="flex items-center gap-2 text-xs text-[#374151] py-1 px-2 rounded-lg hover:bg-[#f3f4f6]"
              >
                <span class="flex-1 truncate">{{ skills.find(s => s.id === sid)?.display_name || skills.find(s => s.id === sid)?.name || sid.slice(0, 8) }}</span>
                <button
                  type="button"
                  class="text-[#9ca3af] hover:text-red-500 transition-colors flex-shrink-0"
                  @click="selectedSkillIds = selectedSkillIds.filter(id => id !== sid)"
                >
                  ✕
                </button>
              </div>
            </div>

            <div class="h-px bg-[#e5e7eb]/60" />

            <div class="space-y-2">
              <button
                type="button"
                :disabled="publishingSelected"
                class="w-full h-8 rounded-xl bg-[#f3f4f6] text-xs text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:opacity-40"
                @click="batchOpenPublishTabs"
              >
                {{ publishingSelected ? '准备中...' : '批量发布到社区' }}
              </button>
              <button
                type="button"
                :disabled="deletingSkills"
                class="w-full h-8 rounded-xl border border-red-200 bg-white text-xs text-red-500 font-semibold transition-all duration-200 hover:bg-red-50 active:scale-[0.98] disabled:opacity-40"
                @click="batchDeleteSkills"
              >
                {{ deletingSkills ? '删除中...' : '批量删除' }}
              </button>
            </div>

            <div class="h-px bg-[#e5e7eb]/60" />
          </template>
          <!-- 用户级技能列表（默认展开） -->
          <div>
            <button
              class="flex h-8 w-full items-center justify-start gap-1.5 rounded-xl pl-2 pr-2 text-left text-xs font-semibold text-[#4b5563] hover:bg-[#f3f4f6] transition-colors active:scale-95"
              type="button"
              @click="userExpanded = !userExpanded"
            >
              <svg
                :class="['h-3 w-3 flex-shrink-0 text-[#9ca3af] transition-transform duration-200', userExpanded ? 'rotate-90' : '']"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              <span>用户级技能</span>
              <span class="ml-auto text-[10px] bg-[#f3f4f6] text-[#9ca3af] px-1.5 py-0.5 rounded-full">{{ userSkills.length }}</span>
            </button>
            <div
              :class="[
                'overflow-hidden transition-[max-height] duration-300 ease-out',
                userExpanded ? 'max-h-[500px] overflow-y-auto' : 'max-h-0',
              ]"
            >
              <div class="mt-1 space-y-1 pl-1">
                <div v-if="userSkills.length === 0" class="px-4 py-2 text-xs text-[#9ca3af]">
                  暂无用户级技能
                </div>
                <div
                  v-for="skill in userSkills"
                  :key="'user-' + skill.name"
                  role="button"
                  tabindex="0"
                  class="flex h-8 items-center gap-2 rounded-xl pl-3 pr-2 text-left transition-colors text-xs text-[#4b5563] hover:bg-[#f3f4f6] cursor-pointer"
                  @click="openSkillEditor('user', skill)"
                >
                  <svg class="h-3.5 w-3.5 flex-shrink-0 text-[#9ca3af]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  <span class="flex-1 truncate">{{ skill.display_name || skill.name }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="h-px bg-[#e5e7eb]/60" />

          <!-- 项目级技能列表 -->
          <div>
            <button
              class="flex h-8 w-full items-center justify-start gap-1.5 rounded-xl pl-2 pr-2 text-left text-xs font-semibold text-[#4b5563] hover:bg-[#f3f4f6] transition-colors active:scale-95"
              type="button"
              @click="projectExpanded = !projectExpanded"
            >
              <svg
                :class="['h-3 w-3 flex-shrink-0 text-[#9ca3af] transition-transform duration-200', projectExpanded ? 'rotate-90' : '']"
                aria-hidden="true"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              <span>项目级技能</span>
              <span class="ml-auto text-[10px] bg-[#f3f4f6] text-[#9ca3af] px-1.5 py-0.5 rounded-full">{{ projects.length }}</span>
            </button>
            <div
              :class="[
                'overflow-hidden transition-[max-height] duration-300 ease-out',
                projectExpanded ? 'max-h-[1000px] overflow-y-auto' : 'max-h-0',
              ]"
            >
              <div class="mt-1.5 space-y-2 pl-1">
                <div v-if="projects.length === 0" class="px-4 py-2 text-xs text-[#9ca3af]">
                  暂无项目
                </div>
                <!-- 拖拽目标容器，支持高亮和放置 -->
                <div
                  v-for="project in sortedProjects"
                  :key="project.pid"
                  class="rounded-xl border border-dashed p-2.5 transition-all duration-200"
                  :class="[
                    activeDragPid === project.pid
                      ? 'border-blue-500 bg-blue-50/50 scale-[1.01]'
                      : 'border-[#e5e7eb] hover:border-gray-400 bg-transparent'
                  ]"
                  @dragover.prevent
                  @dragenter.prevent="activeDragPid = project.pid"
                  @dragleave="activeDragPid = null"
                  @drop="onDrop($event, project.pid)"
                >
                  <!-- 项目标题行 -->
                  <div class="flex items-center gap-2 justify-between">
                    <div
                      class="flex items-center gap-1.5 min-w-0 flex-1 cursor-pointer select-none"
                      @click="toggleProjectSublist(project.pid)"
                    >
                      <!-- 展开项目子技能 -->
                      <button
                        type="button"
                        class="h-4 w-4 flex items-center justify-center text-gray-400 hover:text-gray-600 rounded transition-transform duration-200 pointer-events-none"
                        :class="expandedProjectPids[project.pid] ? 'rotate-90' : ''"
                      >
                        <svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                      <span class="text-xs font-semibold text-gray-700 truncate" :title="project.projectname">
                        {{ project.projectname }}
                      </span>
                    </div>

                    <!-- 批量选择 Checkbox -->
                    <input
                      type="checkbox"
                      :value="project.pid"
                      v-model="selectedProjectIds"
                      @click.stop
                      class="h-3.5 w-3.5 rounded text-[#1f2937] focus:ring-[#1f2937]/20 border-gray-300 cursor-pointer"
                    />
                  </div>

                  <!-- 项目内已安装技能列表 -->
                  <div v-if="expandedProjectPids[project.pid]" class="pl-4 space-y-1 border-l border-gray-100 ml-2 mt-1.5">
                    <div v-if="!(project.pid in projectSkillsMap) || projectSkillsMap[project.pid].length === 0" class="text-[10px] text-[#9ca3af] py-0.5">
                      暂无项目级技能
                    </div>
                    <div
                      v-else
                      v-for="skill in projectSkillsMap[project.pid]"
                      :key="'proj-' + project.pid + '-' + skill.name"
                      role="button"
                      tabindex="0"
                      class="flex h-7 items-center gap-1.5 rounded-lg px-2 text-[11px] text-gray-600 hover:bg-[#f3f4f6] truncate cursor-pointer"
                      @click="openSkillEditor('project', skill, project.pid)"
                    >
                      <svg class="h-3 w-3 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                      </svg>
                      <span class="flex-1 truncate">{{ skill.display_name || skill.name }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 侧边栏底部操作区 -->
        <div class="flex-shrink-0 bg-white border-t border-[#e5e7eb] p-3.5 flex flex-col gap-2">
          <!-- 批量选择状态提示 -->
          <div class="text-[11px] text-gray-500 flex justify-between items-center px-1">
            <span>已选技能: <strong class="text-gray-700 font-semibold">{{ selectedSkillIds.length }}</strong></span>
            <span>已选项目: <strong class="text-gray-700 font-semibold">{{ selectedProjectIds.length }}</strong></span>
          </div>
          <!-- 批量安装按钮 -->
          <button
            class="w-full h-9 rounded-xl bg-[#1f2937] text-xs text-white font-semibold flex items-center justify-center gap-1.5 transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="selectedSkillIds.length === 0 || selectedProjectIds.length === 0 || installingBatch"
            type="button"
            @click="batchInstall"
          >
            <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{{ installingBatch ? '正在安装...' : '批量安装到选中项目' }}</span>
          </button>
        </div>
      </div>
    </aside>
  </div>
</template>

<style>
/* 技能编辑器滑入/滑出动画：从左侧展开，向右收缩 */
.skill-editor-enter-active {
  transition: transform 0.3s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.25s ease;
}
.skill-editor-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 1, 1), opacity 0.2s ease;
}
.skill-editor-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}
.skill-editor-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
