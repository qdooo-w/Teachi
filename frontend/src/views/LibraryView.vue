<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  type UserLibrarySkill,
  type LibrarySkillSort,
  listLibrarySkills,
  getLibrarySkill,
  installLibrarySkill,
  getErrorMessage,
  getCurrentUserId,
  uploadLibrarySkillZip,
  collectLibrarySkill,
  matchLibrarySkillTemplate,
  parseRuntimeSkill,
  updateLibrarySkillMeta,
  bulkDeleteLibrarySkills,
} from '../api'
import { listSkills } from '../skills'
import { useProjects } from '../composables/useProjects'
import { useNotification } from '../composables/useNotification'
import { useUserSkills } from '../composables/useUserSkills'
import LibraryUploadDialog from '../components/LibraryUploadDialog.vue'
import SkillEditorPanel from '../components/SkillEditorPanel.vue'
import { useChatSkillSidebar } from '../composables/useChatSkillSidebar'

const { projects, loadProjects } = useProjects()
const { showError, showSuccess } = useNotification()
const { skills: userSkills, load: loadUserSkills } = useUserSkills()

// ── 标签页系统 ──────────────────────────────────────────────────────────
interface Tab {
  id: string
  type: 'main' | 'skill' | 'import-console' | 'pending-import'
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
    source: 'zip' | 'runtime'
    templateMatched?: boolean
    matchedTemplate?: UserLibrarySkill | null
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
  if (!confirm(`确定删除选中的 ${count} 个技能？此操作不可撤销。`)) return

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
const installing = ref(false)
const installingProject = ref(false)
const selectedProjectId = ref('')

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
  return skill.community_skill_id ? '来自社区' : '本地收集'
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
  try {
    detailSkill.value = await getLibrarySkill(id)
  } catch (e) {
    showError('加载详情失败', getErrorMessage(e))
  } finally {
    detailLoading.value = false
  }
}

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

// ── Fork ────────────────────────────────────────────────────────────────
function doFork(): void {
  if (!detailSkill.value) return
  const skill = detailSkill.value
  const newTabId = `pending-import:${skill.name}:${Date.now()}-${Math.random().toString(36).substr(2, 5)}`

  const originalDisplayName = skill.display_name || skill.name
  let newDisplayName = ''
  const suffixMatch = originalDisplayName.match(/ \(自定义版本 (\d+)\)$/)
  if (suffixMatch) {
    const nextNum = parseInt(suffixMatch[1], 10) + 1
    newDisplayName = originalDisplayName.replace(/ \(自定义版本 (\d+)\)$/, ` (自定义版本 ${nextNum})`)
  } else {
    newDisplayName = `${originalDisplayName} (自定义版本 1)`
  }

  const newTab: Tab = {
    id: newTabId,
    type: 'pending-import',
    label: `复制：${skill.name}`,
    pendingData: {
      libraryId: '', // 相当于新建，更新 version_id / skill_id
      name: skill.name,
      formName: skill.name,
      formDisplayName: newDisplayName,
      formDescription: skill.description || '',
      formReadmeMd: skill.readme_md || '',
      formTags: parseTags(skill.tags),
      formVersion: skill.version || '1.0.0',
      source: 'runtime',
      templateMatched: false,
      matchedTemplate: null,
    },
    lastAccessed: Date.now(),
  }

  tabs.value.push(newTab)
  saveTabs(tabs.value)
  activeTabId.value = newTabId
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
  }
}

const importQueue = ref<ImportQueueItem[]>([])
const runtimeSelectedSkillNames = ref<string[]>([])
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
          }
        } else if (item.source === 'runtime') {
          const res = await parseRuntimeSkill(item.name)
          item.status = 'success'
          item.parsedData = {
            name: res.frontmatter.name,
            displayName: res.frontmatter.display_name || res.frontmatter.name,
            readmeMd: res.frontmatter.body || '',
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
        formDescription: '',
        formReadmeMd: data.readmeMd || '',
        formTags: [],
        formVersion: '1.0.0',
        source: item.source,
        templateMatched: false,
        matchedTemplate: null,
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
  if (!/^[a-zA-Z0-9_-]+$/.test(data.formName.trim())) {
    showError('技能标识名只能包含字母、数字、下划线和中划线')
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
  if (!data.formVersion.trim()) {
    showError('版本号不能为空')
    return
  }
  if (!/^[0-9]+\.[0-9]+\.[0-9]+$/.test(data.formVersion.trim())) {
    showError('版本号格式必须为 X.Y.Z (例如 1.0.0)')
    return
  }

  isSavingPending.value = true
  try {
    const tagsJson = JSON.stringify(data.formTags)
    let finalSkillId = ''

    if (data.source === 'runtime') {
      const res = await collectLibrarySkill({
        skill_name: data.name,
        name: data.formName,
        display_name: data.formDisplayName,
        description: data.formDescription,
        readme_md: data.formReadmeMd,
        tags: tagsJson,
        version: data.formVersion,
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
        version: data.formVersion,
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

function cancelPendingImport(tabId: string): void {
  if (confirm('是否确定放弃导入该技能包？配置将不会被保存。')) {
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
          key="editor"
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

            <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
              <button
                v-for="s in skills"
                :key="s.id"
                draggable="true"
                @dragstart="onDragStart($event, s)"
                class="flex w-full flex-col gap-2 rounded-xl bg-white p-3.5 text-left shadow-sm transition hover:bg-[#f9fafb] hover:shadow-md active:scale-[0.99] relative group cursor-grab"
                type="button"
                @click="openSkillTab(s)"
              >
                <!-- 标题行 -->
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center gap-1.5 min-w-0">
                    <!-- 批量选择 Checkbox -->
                    <input
                      type="checkbox"
                      :value="s.id"
                      v-model="selectedSkillIds"
                      @click.stop
                      class="h-3.5 w-3.5 flex-shrink-0 rounded text-[#1f2937] focus:ring-[#1f2937]/20 border-gray-300 cursor-pointer"
                    />
                    <span class="truncate text-sm font-semibold text-[#1f2937]">{{ skillTitle(s) }}</span>
                  </div>
                  <span
                    class="flex flex-shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] whitespace-nowrap"
                    :class="s.community_skill_id ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
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
                      <span class="rounded-sm bg-[#f3f4f6] px-1.5 py-0.5 text-[10px] text-[#9ca3af] truncate max-w-[60px]">
                        {{ tag }}
                      </span>
                    </template>
                  </div>
                  <div class="flex flex-shrink-0 items-center gap-1.5 text-[10px] text-[#9ca3af] tabular-nums">
                    <span>v{{ s.version }}</span>
                    <span>·</span>
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
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              <!-- ZIP 压缩包上传 -->
              <div 
                @dragover.prevent
                @drop="handleZipDrop"
                class="flex flex-col items-center justify-center border-2 border-dashed border-[#d1d5db] rounded-2xl bg-white p-6 transition-all hover:border-[#1f2937] hover:bg-gray-50/50 group relative cursor-pointer"
              >
                <input 
                  type="file" 
                  accept=".zip" 
                  multiple 
                  class="absolute inset-0 opacity-0 cursor-pointer" 
                  @change="handleZipSelect"
                />
                <div class="flex h-12 w-12 items-center justify-center rounded-full bg-[#f3f4f6] text-[#4b5563] mb-4 group-hover:scale-105 transition-transform">
                  <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 18h16" />
                  </svg>
                </div>
                <span class="text-sm font-medium text-[#1f2937]">点击选择或将 ZIP 拖拽到这里</span>
                <span class="text-xs text-[#9ca3af] mt-1">支持多选，大小不超过 40MB</span>
              </div>

              <!-- 本地运行层导入 -->
              <div class="flex flex-col rounded-2xl border border-[#e5e7eb] bg-white p-6 shadow-sm">
                <div class="flex h-10 w-10 items-center justify-center rounded-full bg-[#f3f4f6] text-[#4b5563] mb-4">
                  <svg class="h-5 w-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <h3 class="text-sm font-medium text-[#1f2937] mb-1">从本地运行层导入</h3>
                <p class="text-xs text-[#9ca3af] mb-4">选择本地正在运行的技能进行配置导入，作为新版本或独立副本。</p>
                
                <!-- 1. 来源选择 -->
                <div class="mb-3">
                  <label class="block text-[11px] font-semibold text-[#4b5563] mb-1">技能来源（用户/项目）：</label>
                  <select
                    v-model="importSourceType"
                    class="block w-full rounded-xl border border-[#d1d5db] bg-transparent px-3 py-1.5 text-xs text-[#1f2937] outline-none focus:ring-1 focus:ring-[#1f2937]"
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
                  <label class="block text-[11px] font-semibold text-[#4b5563] mb-1">选择技能：</label>
                  <div class="flex gap-2">
                    <div class="relative flex-1 min-w-0">
                      <div v-if="loadingSourceSkills" class="text-xs text-[#9ca3af] py-4 text-center">
                        正在载入本地技能...
                      </div>
                      <select
                        v-else
                        v-model="runtimeSelectedSkillNames"
                        multiple
                        class="block w-full rounded-xl border border-[#d1d5db] bg-transparent px-3 py-1.5 text-xs text-[#1f2937] outline-none min-h-[90px] focus:ring-1 focus:ring-[#1f2937]"
                      >
                        <option 
                          v-for="s in importSourceSkills" 
                          :key="s.name" 
                          :value="s.name"
                        >
                          {{ s.display_name || s.name }} ({{ s.name }})
                        </option>
                      </select>
                      <div v-if="!loadingSourceSkills && importSourceSkills.length === 0" class="text-[10px] text-red-500 mt-1">
                        ⚠️ 选中的项目空间下无本地技能
                      </div>
                    </div>
                    <button
                      type="button"
                      :disabled="runtimeSelectedSkillNames.length === 0 || loadingSourceSkills"
                      @click="addRuntimeSkillsToQueue"
                      class="h-8 rounded-xl bg-[#1f2937] px-3 text-xs font-medium text-white transition hover:bg-[#111827] active:scale-95 disabled:opacity-40 disabled:scale-100 flex-shrink-0"
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
                    class="h-7 px-2.5 rounded-xl border border-gray-200 text-[10px] font-medium text-gray-500 hover:bg-gray-50 transition active:scale-95 disabled:opacity-40"
                  >
                    清空全部
                  </button>
                  <button
                    type="button"
                    @click="startQueueImport"
                    :disabled="isUploading || !importQueue.some(q => q.status === 'success')"
                    class="h-7 px-3 rounded-xl bg-purple-600 text-[10px] font-medium text-white transition hover:bg-purple-700 active:scale-95 disabled:opacity-40 shadow-sm shadow-purple-100 flex items-center gap-1"
                  >
                    <svg class="h-3 w-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
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
                  placeholder="仅限字母、数字、下划线和中划线"
                  class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                />
                <span class="text-[10px] text-[#9ca3af] block mt-1">技能的唯一英文标识，将作为后端物理文件中的 SKILL.md name 配置项。</span>
              </div>

              <!-- version (可编辑) -->
              <div>
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">版本号 (version) <span class="text-red-500">*</span></label>
                <input
                  v-model="currentPendingData.formVersion"
                  type="text"
                  placeholder="格式如：1.0.0"
                  class="block w-full rounded-none border border-[#e5e7eb] bg-white px-3 py-2 text-xs text-[#1f2937] placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] focus:ring-1 focus:ring-[#1f2937]"
                />
                <span class="text-[10px] text-[#9ca3af] block mt-1">请使用三位版本号规范（例如：1.0.0）。</span>
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
                <label class="block text-xs font-semibold text-[#4b5563] mb-1.5">简短描述 (description) <span class="text-red-500">*</span></label>
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
        
        <!-- ── 技能详情标签页 ── -->
        <template v-else-if="activeTab.type === 'skill'">
          <!-- 顶部栏 -->
          <div class="flex flex-shrink-0 items-center h-9 px-5 gap-2 bg-white font-hans">
            <span class="!text-xs font-semibold text-[#1f2937]">{{ detailSkill ? skillTitle(detailSkill) : '加载中...' }}</span>
            <span
              v-if="detailSkill"
              class="rounded-full px-2 py-0.5 !text-xs whitespace-nowrap"
              :class="detailSkill.community_skill_id ? 'bg-blue-50 text-blue-600' : 'bg-[#f3f4f6] text-[#6b7280]'"
            >
              {{ sourceLabel(detailSkill) }}
            </span>
          </div>
          <!-- 内容 -->
          <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <!-- 加载态 -->
            <div v-if="detailLoading" class="flex h-full items-center justify-center text-sm text-[#9ca3af]">
              加载中...
            </div>

            <template v-else-if="detailSkill">
              <div class="flex flex-col lg:flex-row h-full gap-4 items-start">
                <!-- 左侧/主体：README 与描述 -->
                <div class="flex-1 min-w-0 w-full bg-white rounded-xl border border-[#e5e7eb] p-6 flex flex-col">

                  <p v-if="detailSkill.description" class="mb-4 rounded-lg bg-[#f9fafb] px-4 py-3 text-sm text-[#374151] leading-relaxed">
                    {{ detailSkill.description }}
                  </p>

                  <div v-if="detailSkill.readme_md" class="mt-4 flex-1">
                    <div class="mb-2 text-xs font-semibold text-[#9ca3af] uppercase tracking-wider">README</div>
                    <div class="rounded-xl border border-[#e5e7eb] bg-[#fafafa] p-4 text-sm text-[#374151] leading-relaxed overflow-y-auto max-h-[400px]">
                      <pre class="whitespace-pre-wrap font-sans text-sm text-[#374151]">{{ detailSkill.readme_md }}</pre>
                    </div>
                  </div>
                  <div v-else class="py-12 text-center text-sm text-[#9ca3af]">
                    暂无 README 内容
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
                      class="w-full rounded-xl bg-[#f3f4f6] py-2.5 text-sm text-[#374151] font-semibold transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
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

                    <button
                      class="w-full h-9 rounded-xl bg-[#1f2937] text-xs text-white font-semibold transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 mt-1"
                      :disabled="installing"
                      type="button"
                      @click="doInstall"
                    >
                      {{ installing ? '安装中...' : '安装到用户级技能' }}
                    </button>
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
          <span class="text-sm font-semibold text-[#1f2937]">技能与项目</span>
        </div>

        <!-- 侧边栏滚动列表 -->
        <div class="flex-1 overflow-y-auto px-3 py-4 space-y-4">
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
