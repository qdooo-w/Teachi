<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import {
  type CommunitySkillSummary,
  type CommunitySkillDetail,
  type CommunitySort,
  type CommunityComment,
  listCommunitySkills,
  getCommunitySkill,
  likeCommunitySkill,
  installCommunitySkill,
  deleteCommunitySkill,
  listCommunityComments,
  createCommunityComment,
  deleteCommunityComment,
  likeCommunityComment,
  reportCommunityComment,
  getCurrentUserId,
  getErrorMessage,
} from '../api'
import { COMMUNITY_PAGE_LIMIT } from '../config'
import { useProjects } from '../composables/useProjects'
import { useNotification } from '../composables/useNotification'
import { renderMarkdown } from '../markdown/renderer'

// ── 项目列表（安装到项目时使用） ──────────────────────────────────────────
const { projects, loadProjects } = useProjects()
const { showError, showSuccess } = useNotification()

// ── 当前用户 ────────────────────────────────────────────────────────────
const currentUserId = ref<string | null>(getCurrentUserId())

// ── 标签页系统（模块级持久化，路由切换不丢失） ──────────────────────────
interface Tab {
  id: string
  type: 'main' | 'skill'
  label: string
  skillId?: string
  lastAccessed: number
}

const TAB_TTL = 5 * 3600 * 1000 // 5 小时自动清除

/** 模块级缓存：技能详情数据，关闭标签时清空 */
const skillCache = new Map<string, CommunitySkillDetail>()

/** 从 sessionStorage 恢复或新建 */
function loadTabs(): Tab[] {
  try {
    const raw = sessionStorage.getItem('community-tabs')
    if (raw) {
      const parsed: Tab[] = JSON.parse(raw)
      const now = Date.now()
      const valid = parsed.filter((t) => t.type === 'main' || (t.type === 'skill' && now - t.lastAccessed < TAB_TTL))
      if (valid.length > 0 && valid[0].type === 'main') return valid
    }
  } catch { /* ignore */ }
  return [{ id: 'main', type: 'main', label: '主界面', lastAccessed: Date.now() }]
}

function saveTabs(t: Tab[]): void {
  try { sessionStorage.setItem('community-tabs', JSON.stringify(t)) } catch { /* ignore */ }
}

const tabs = ref<Tab[]>(loadTabs())
const activeTabId = ref(tabs.value[0]?.id ?? 'main')

const activeTab = computed(() => tabs.value.find((t) => t.id === activeTabId.value) ?? tabs.value[0])

/** 当前激活的技能详情 */
const skillDetail = ref<CommunitySkillDetail | null>(null)
const detailLoading = ref(false)

function openTab(tab: Tab): void {
  tab.lastAccessed = Date.now()
  saveTabs(tabs.value)
  activeTabId.value = tab.id
}

function openSkillTab(skill: CommunitySkillSummary): void {
  const existing = tabs.value.find((t) => t.type === 'skill' && t.skillId === skill.id)
  if (existing) {
    existing.lastAccessed = Date.now()
    saveTabs(tabs.value)
    activeTabId.value = existing.id
    return
  }
  const label = skill.display_name || skill.name
  const newTab: Tab = { id: `skill:${skill.id}`, type: 'skill', label, skillId: skill.id, lastAccessed: Date.now() }
  tabs.value.push(newTab)
  saveTabs(tabs.value)
  activeTabId.value = newTab.id
}

function closeTab(tabId: string): void {
  if (tabId === 'main') return
  const idx = tabs.value.findIndex((t) => t.id === tabId)
  if (idx === -1) return

  // 清除该标签对应的缓存数据，释放内存
  const tab = tabs.value[idx]
  if (tab.skillId) {
    skillCache.delete(tab.skillId)
  }
  // 如果正在显示这个技能，清空当前详情
  if (tab.skillId && skillDetail.value?.id === tab.skillId) {
    skillDetail.value = null
  }

  tabs.value.splice(idx, 1)
  saveTabs(tabs.value)

  if (activeTabId.value === tabId) {
    const next = tabs.value[Math.min(idx, tabs.value.length - 1)]
    activeTabId.value = next?.id ?? 'main'
  }
}

// ── 搜索 ────────────────────────────────────────────────────────────────
const keyword = ref('')

// ── 列表状态 ────────────────────────────────────────────────────────────
const skills = ref<CommunitySkillSummary[]>([])
const total = ref(0)
const loading = ref(false)
// ── 排序/筛选状态 ──────────────────────────────────────────────────────
const sort = ref<CommunitySort>('popular')
const offset = ref(0)
const limit = COMMUNITY_PAGE_LIMIT
const selectedTags = ref<string[]>([])
const showTagFilter = ref(false)
const tagInputText = ref('')
const tagInputRef = ref<HTMLInputElement | null>(null)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / limit)))
const currentPage = computed(() => Math.floor(offset.value / limit) + 1)

// ── 解析 tags 字段（后端返回 JSON 字符串或数组） ─────────────────────────
function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ── 技能标题 ────────────────────────────────────────────────────────────
function skillTitle(skill: { name: string; display_name?: string | null }): string {
  return skill.display_name || skill.name
}

// ── 格式化 ──────────────────────────────────────────────────────────────
function formatBytes(n: number | null | undefined): string {
  if (n == null || n <= 0) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(ts: number): string {
  const d = new Date(ts * 1000)
  const now = Date.now()
  const diff = now - d.getTime()
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 30) return `${days} 天前`
  return d.toLocaleDateString('zh-CN')
}

// ── 加载技能列表 ──────────────────────────────────────────────────────────
async function loadSkills(): Promise<void> {
  loading.value = true
  try {
    const kw = keyword.value.trim()
    const r = await listCommunitySkills({
      keyword: kw || undefined,
      limit,
      offset: offset.value,
      sort: sort.value,
      tags: selectedTags.value.length > 0 ? selectedTags.value : undefined,
    })
    skills.value = r.skills
    total.value = r.total
  } catch (e) {
    showError('加载技能列表失败', getErrorMessage(e))
  } finally {
    loading.value = false
  }
}

// ── 加载技能详情（优先用缓存） ──────────────────────────────────────────
async function loadSkillDetail(skillId: string): Promise<void> {
  // 命中缓存直接恢复
  const cached = skillCache.get(skillId)
  if (cached) {
    skillDetail.value = cached
    return
  }
  detailLoading.value = true
  try {
    skillDetail.value = await getCommunitySkill(skillId)
    if (skillDetail.value) {
      skillCache.set(skillId, skillDetail.value)
    }
    const tab = tabs.value.find((t) => t.skillId === skillId)
    if (tab && skillDetail.value) {
      tab.label = skillTitle(skillDetail.value)
      saveTabs(tabs.value)
    }
  } catch (e) {
    showError('加载技能详情失败', getErrorMessage(e))
  } finally {
    detailLoading.value = false
  }
}

// ── 点赞/取消技能 ──────────────────────────────────────────────────────
async function toggleSkillLike(): Promise<void> {
  if (!skillDetail.value) return
  try {
    const r = await likeCommunitySkill(skillDetail.value.id)
    skillDetail.value.liked_by_me = r.liked
    skillDetail.value.likes += r.liked ? 1 : -1
    // 同步更新列表中的计数
    const inList = skills.value.find((s) => s.id === skillDetail.value!.id)
    if (inList) {
      inList.likes = skillDetail.value.likes
      inList.liked_by_me = r.liked
    }
  } catch (e) {
    showError('操作失败', getErrorMessage(e))
  }
}

// ── 安装 ────────────────────────────────────────────────────────────────
const installing = ref(false)
const installingProject = ref(false)
const selectedProjectId = ref('')
const installMsg = ref('')

async function doInstall(target: 'user' | 'project'): Promise<void> {
  if (!skillDetail.value) return
  if (target === 'project' && !selectedProjectId.value) return

  if (target === 'user') installing.value = true
  else installingProject.value = true
  installMsg.value = ''

  try {
    const payload = target === 'project'
      ? { target: 'project' as const, pid: selectedProjectId.value }
      : { target: 'user' as const }
    const r = await installCommunitySkill(skillDetail.value.id, payload)
    skillDetail.value.downloads = r.downloads
    const inList = skills.value.find((s) => s.id === skillDetail.value!.id)
    if (inList) inList.downloads = r.downloads
    installMsg.value = `已安装：${r.name}`
    showSuccess(installMsg.value)
  } catch (e) {
    installMsg.value = ''
    showError('安装失败', getErrorMessage(e))
  } finally {
    installing.value = false
    installingProject.value = false
  }
}

// ── 删除社区技能 ──────────────────────────────────────────────────────
const deleting = ref(false)

async function doDelete(): Promise<void> {
  if (!skillDetail.value) return
  if (!confirm(`确定要删除社区中的 "${skillTitle(skillDetail.value)}" 吗？此操作不可撤销。`)) return
  deleting.value = true
  try {
    await deleteCommunitySkill(skillDetail.value.id)
    showSuccess('已删除')
    const tabId = `skill:${skillDetail.value.id}`
    closeTab(tabId)
    skillDetail.value = null
    await loadSkills()
  } catch (e) {
    showError('删除失败', getErrorMessage(e))
  } finally {
    deleting.value = false
  }
}

// ── 评论系统 ────────────────────────────────────────────────────────────
const comments = ref<CommunityComment[]>([])
const commentsLoading = ref(false)
const commentContent = ref('')
const commentSubmitting = ref(false)
/** 正在回复的评论 ID */
const replyingTo = ref<string | null>(null)
const replyContent = ref('')
const replySubmitting = ref(false)
/** 举报弹窗 */
const reportTarget = ref<CommunityComment | null>(null)
const reportReason = ref('')
const reportDetail = ref('')
const reportSubmitting = ref(false)

/** 将扁平评论列表组装成树形结构 */
function buildCommentTree(flat: CommunityComment[]): CommunityComment[] {
  const map = new Map<string, CommunityComment>()
  const roots: CommunityComment[] = []
  for (const c of flat) {
    map.set(c.id, { ...c, replies: [] })
  }
  for (const c of flat) {
    const node = map.get(c.id)!
    if (c.parent_id && map.has(c.parent_id)) {
      map.get(c.parent_id)!.replies!.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

async function loadComments(): Promise<void> {
  if (!skillDetail.value) return
  commentsLoading.value = true
  try {
    const flat = await listCommunityComments(skillDetail.value.id)
    // 检查后端是否已经返回树形结构
    const isTree = flat.length > 0 && flat[0].replies !== undefined &&
      flat.some((c) => c.depth === 0 && Array.isArray(c.replies))
    if (isTree) {
      comments.value = flat
    } else {
      comments.value = buildCommentTree(flat)
    }
  } catch (e) {
    showError('加载评论失败', getErrorMessage(e))
  } finally {
    commentsLoading.value = false
  }
}

async function submitComment(): Promise<void> {
  if (!skillDetail.value || !commentContent.value.trim()) return
  commentSubmitting.value = true
  try {
    await createCommunityComment(skillDetail.value.id, {
      content: commentContent.value.trim(),
    })
    commentContent.value = ''
    await loadComments()
  } catch (e) {
    showError('发表评论失败', getErrorMessage(e))
  } finally {
    commentSubmitting.value = false
  }
}

async function submitReply(parentId: string, replyToUuid: string | null): Promise<void> {
  if (!skillDetail.value || !replyContent.value.trim()) return
  replySubmitting.value = true
  try {
    await createCommunityComment(skillDetail.value.id, {
      content: replyContent.value.trim(),
      parent_id: parentId,
      reply_to_uuid: replyToUuid,
    })
    replyContent.value = ''
    replyingTo.value = null
    await loadComments()
  } catch (e) {
    showError('回复失败', getErrorMessage(e))
  } finally {
    replySubmitting.value = false
  }
}

async function toggleCommentLike(comment: CommunityComment): Promise<void> {
  try {
    const r = await likeCommunityComment(comment.id)
    comment.likes += r.liked ? 1 : -1
    comment.liked_by_me = r.liked
  } catch (e) {
    showError('操作失败', getErrorMessage(e))
  }
}

async function doDeleteComment(comment: CommunityComment): Promise<void> {
  if (!skillDetail.value || !confirm('确定要删除这条评论吗？')) return
  try {
    await deleteCommunityComment(skillDetail.value.id, comment.id)
    await loadComments()
  } catch (e) {
    showError('删除评论失败', getErrorMessage(e))
  }
}

function openReport(comment: CommunityComment): void {
  reportTarget.value = comment
  reportReason.value = ''
  reportDetail.value = ''
}

function closeReport(): void {
  reportTarget.value = null
}

async function submitReport(): Promise<void> {
  if (!reportTarget.value || !reportReason.value.trim()) return
  reportSubmitting.value = true
  try {
    await reportCommunityComment(reportTarget.value.id, {
      reason: reportReason.value.trim(),
      detail: reportDetail.value.trim() || undefined,
    })
    showSuccess('举报已提交')
    closeReport()
  } catch (e) {
    showError('举报失败', getErrorMessage(e))
  } finally {
    reportSubmitting.value = false
  }
}

// ── 排序切换 ────────────────────────────────────────────────────────────
function changeSort(next: CommunitySort): void {
  if (sort.value === next) return
  sort.value = next
  offset.value = 0
  void loadSkills()
}

// ── 标签筛选 ────────────────────────────────────────────────────────────
function toggleTagFilter(): void {
  showTagFilter.value = !showTagFilter.value
  if (showTagFilter.value) {
    // 打开时聚焦输入框
    void nextTick(() => tagInputRef.value?.focus())
  } else {
    // 关闭时清除所有标签
    if (selectedTags.value.length > 0) {
      selectedTags.value = []
      offset.value = 0
      void loadSkills()
    }
  }
}

function addTag(): void {
  const tag = tagInputText.value.trim().toLowerCase()
  if (!tag || selectedTags.value.includes(tag)) return
  selectedTags.value = [...selectedTags.value, tag]
  tagInputText.value = ''
  offset.value = 0
  void loadSkills()
}

function removeTag(tag: string): void {
  selectedTags.value = selectedTags.value.filter((t) => t !== tag)
  offset.value = 0
  void loadSkills()
}

// ── 搜索提交 ────────────────────────────────────────────────────────────
function submitSearch(): void {
  offset.value = 0
  void loadSkills()
}

// ── 翻页 ────────────────────────────────────────────────────────────────
function gotoPage(page: number): void {
  const p = Math.max(1, Math.min(totalPages.value, page))
  offset.value = (p - 1) * limit
  void loadSkills()
}

/** 生成翻页按钮序列（始终显示第一页和最后一页，当前页前后各 2 页） */
const pageNumbers = computed(() => {
  const pages: number[] = []
  const tp = totalPages.value
  const cp = currentPage.value
  if (tp <= 7) {
    for (let i = 1; i <= tp; i++) pages.push(i)
  } else {
    pages.push(1)
    const start = Math.max(2, cp - 1)
    const end = Math.min(tp - 1, cp + 1)
    if (start > 2) pages.push(-1) // 省略号
    for (let i = start; i <= end; i++) pages.push(i)
    if (end < tp - 1) pages.push(-1)
    pages.push(tp)
  }
  return pages
})

// ── 切换标签时加载数据 ──────────────────────────────────────────────────
watch(activeTabId, async (newId) => {
  const tab = tabs.value.find((t) => t.id === newId)
  if (tab) {
    tab.lastAccessed = Date.now()
    saveTabs(tabs.value)
  }
  if (tab?.type === 'skill' && tab.skillId) {
    skillDetail.value = null
    installMsg.value = ''
    commentContent.value = ''
    replyingTo.value = null
    await loadSkillDetail(tab.skillId)
    await loadComments()
  }
})

// ── 判断当前用户是否为技能作者 ──────────────────────────────────────────
const isAuthor = computed(() => skillDetail.value?.owner_uuid === currentUserId.value)

// 统计评论总数（含回复）
const totalCommentCount = computed(() => {
  let count = 0
  function walk(list: CommunityComment[]): void {
    for (const c of list) {
      count++
      if (c.replies) walk(c.replies)
    }
  }
  walk(comments.value)
  return count
})

// ── 定时清除超过 5h 未访问的标签 ────────────────────────────────────────
let cleanupTimer: ReturnType<typeof setInterval> | null = null

function cleanupExpiredTabs(): void {
  const now = Date.now()
  const before = tabs.value.length
  const removedIds: string[] = []
  tabs.value = tabs.value.filter((t) => {
    if (t.type === 'main') return true
    if (now - t.lastAccessed > TAB_TTL) {
      if (t.skillId) {
        skillCache.delete(t.skillId)
        removedIds.push(t.skillId)
      }
      return false
    }
    return true
  })
  if (tabs.value.length < before) {
    saveTabs(tabs.value)
    // 如果当前激活的标签被清除了，切到主界面
    const stillExists = tabs.value.find((t) => t.id === activeTabId.value)
    if (!stillExists) {
      activeTabId.value = 'main'
      skillDetail.value = null
    }
    // 清除被移除标签对应的评论状态
    if (removedIds.includes(skillDetail.value?.id ?? '')) {
      skillDetail.value = null
    }
  }
}

// ── 初始化 ──────────────────────────────────────────────────────────────
onMounted(() => {
  document.title = '社区 · Learnova'
  void loadSkills()
  void loadProjects()
  // 立即清理一次过期标签，然后每 10 分钟检查
  cleanupExpiredTabs()
  cleanupTimer = setInterval(cleanupExpiredTabs, 10 * 60 * 1000)
})

onBeforeUnmount(() => {
  if (cleanupTimer) {
    clearInterval(cleanupTimer)
    cleanupTimer = null
  }
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-[#f3f4f6]">
    <!-- ═══ 顶栏：居中搜索框 ═══ -->
    <div class="relative flex h-14 flex-shrink-0 items-center bg-transparent px-6">
      <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center gap-3">
        <div class="relative flex items-center bg-[#e5e7eb]/70 hover:bg-[#e5e7eb] focus-within:bg-white focus-within:ring-2 focus-within:ring-[#9ca3af]/20 transition-all rounded-2xl w-72 h-8">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg class="h-4 w-4 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <input
            v-model="keyword"
            class="block w-full rounded-2xl bg-transparent py-1 pl-9 pr-3 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none"
            placeholder="搜索技能名或描述"
            type="search"
            @keyup.enter="submitSearch"
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
        <span class="max-w-[160px] truncate">{{ tab.label }}</span>
        <span
          v-if="tab.type !== 'main'"
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
        <!-- 筛选栏 -->
        <div class="flex flex-shrink-0 items-center gap-2 px-5 py-2 bg-white">
          <select
            :value="sort"
            class="h-7 py-0 leading-none border-0 border-b-2 border-[#e5e7eb] bg-transparent pl-0 pr-4 text-xs text-[#4b5563] outline-none cursor-pointer hover:border-[#1f2937] transition-colors duration-200 font-hans"
            @change="changeSort(($event.target as HTMLSelectElement).value as CommunitySort)"
          >
            <option value="popular">热门 (下载量)</option>
            <option value="newest">最新发布</option>
            <option value="most_liked">最多点赞</option>
          </select>

          <!-- 标签筛选按钮 -->
          <button
            type="button"
            class="flex h-7 items-center gap-1 rounded-none border-0 border-b-2 py-0 pl-0 pr-3 !text-xs leading-none transition-all duration-200 active:scale-95 font-hans"
            :class="showTagFilter
              ? 'border-[#1f2937] text-[#1f2937]'
              : 'border-[#e5e7eb] text-[#6b7280] hover:border-[#1f2937] hover:text-[#1f2937]'"
            @click="toggleTagFilter"
          >
            <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" />
              <line x1="7" y1="7" x2="7.01" y2="7" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            标签
          </button>

          <!-- 已选标签 chip + 输入框 -->
          <template v-if="showTagFilter">
            <span
              v-for="tag in selectedTags"
              :key="tag"
              class="inline-flex items-center gap-0.5 h-7 bg-[#e5e7eb] py-0 px-2 !text-xs text-[#1f2937] leading-none flex-shrink-0 font-hans rounded-sm"
            >
              {{ tag }}
              <button
                type="button"
                class="flex h-4 w-4 items-center justify-center rounded-full text-[#9ca3af] hover:bg-[#d1d5db] hover:text-[#1f2937] transition-colors flex-shrink-0 active:scale-90"
                @click="removeTag(tag)"
              >
                <svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
            <input
              ref="tagInputRef"
              v-model="tagInputText"
              type="text"
              class="h-7 w-32 py-0 leading-none border-0 border-b border-[#e5e7eb] bg-transparent pl-0 pr-2 !text-xs text-[#1f2937] placeholder:!text-xs placeholder:text-[#9ca3af] outline-none focus:border-[#1f2937] transition-colors duration-200 font-hans"
              placeholder="输入标签..."
              @keydown.enter.prevent="addTag"
            />
          </template>

          <span class="text-xs text-[#9ca3af] flex-shrink-0 ml-auto">共 {{ total }} 个技能</span>
        </div>

        <!-- 内容区 -->
        <div class="min-h-0 flex-1 overflow-y-auto px-5 pt-0 pb-4">
          <!-- 加载态 -->
          <div v-if="loading" class="py-16 text-center text-sm text-[#9ca3af]">
            加载中...
          </div>

          <!-- 空态 -->
          <div v-else-if="skills.length === 0" class="py-16 text-center">
            <p class="text-sm text-[#9ca3af]">还没有技能，去技能管理页发布第一个吧。</p>
          </div>

          <!-- 技能卡片列表 -->
          <div v-else class="flex flex-col gap-3">
            <button
              v-for="s in skills"
              :key="s.id"
              type="button"
              class="flex flex-col gap-2.5 py-4 text-left transition-colors duration-200 hover:bg-[#f3f4f6]/50 border-b border-[#e5e7eb] last:border-b-0"
              @click="openSkillTab(s)"
            >
              <!-- 第一行：标题 + 统计 -->
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="truncate text-base font-semibold text-[#1f2937]">{{ skillTitle(s) }}</span>
                  <span
                    v-if="s.latest_version || s.version"
                    class="flex-shrink-0 rounded-md bg-[#f3f4f6] px-1.5 py-0.5 text-[10px] tabular-nums text-[#6b7280]"
                  >
                    v{{ s.latest_version || s.version }}
                  </span>
                </div>
                <div class="flex items-center gap-3 text-xs text-[#6b7280] flex-shrink-0">
                  <span class="flex items-center gap-1 tabular-nums">
                    <svg class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    {{ s.downloads }}
                  </span>
                  <span class="flex items-center gap-1 tabular-nums" :class="{ 'text-[#dc2626]': s.liked_by_me }">
                    <svg class="h-3.5 w-3.5" aria-hidden="true" :fill="s.liked_by_me ? 'currentColor' : 'none'" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    {{ s.likes }}
                  </span>
                </div>
              </div>

              <!-- 描述 -->
              <p class="line-clamp-2 text-sm text-[#6b7280] leading-relaxed">
                {{ s.description || '暂无描述' }}
              </p>

              <!-- 标签 + 时间 -->
              <div class="flex items-center justify-between gap-3">
                <div v-if="parseTags(s.tags).length > 0" class="flex flex-wrap gap-1.5">
                  <span
                    v-for="tag in parseTags(s.tags).slice(0, 5)"
                    :key="tag"
                    class="rounded-md bg-[#f3f4f6] px-2 py-0.5 text-xs text-[#6b7280]"
                  >
                    {{ tag }}
                  </span>
                </div>
                <span v-else class="text-xs text-[#d1d5db]">无标签</span>
                <span class="flex-shrink-0 text-xs text-[#9ca3af]">{{ formatDate(s.updated_at) }} 更新</span>
              </div>
            </button>
          </div>

          <!-- 翻页 -->
          <div v-if="totalPages > 1" class="mt-5 flex items-center justify-center gap-1.5">
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:opacity-40"
              :disabled="currentPage === 1"
              @click="gotoPage(currentPage - 1)"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <template v-for="p in pageNumbers" :key="p">
              <span v-if="p === -1" class="px-1 text-xs text-[#d1d5db]">…</span>
              <button
                v-else
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-xs tabular-nums transition-all duration-200 active:scale-[0.98]"
                :class="p === currentPage
                  ? 'bg-[#1f2937] text-white font-semibold'
                  : 'text-[#6b7280] hover:bg-[#e5e7eb]'"
                @click="gotoPage(p)"
              >
                {{ p }}
              </button>
            </template>
            <button
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-lg text-xs text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:opacity-40"
              :disabled="currentPage === totalPages"
              @click="gotoPage(currentPage + 1)"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </template>

      <!-- ── 技能详情标签页 ── -->
      <template v-else-if="activeTab.type === 'skill'">
        <div class="min-h-0 flex-1 overflow-y-auto">
          <!-- 加载态 -->
          <div v-if="detailLoading" class="flex h-full items-center justify-center text-sm text-[#9ca3af]">
            加载中...
          </div>

          <template v-else-if="skillDetail">
            <div class="flex flex-col lg:flex-row" :class="{ 'lg:h-full': !!skillDetail.readme_md }">
              <!-- 左侧：README 渲染区 -->
              <div
                class="min-h-0 overflow-y-auto px-5 py-4 lg:border-r lg:border-[#e5e7eb]"
                :class="skillDetail.readme_md ? 'flex-1' : 'flex items-center justify-center py-8 lg:flex-1'"
              >
                <div v-if="skillDetail.readme_md" class="markdown-body">
                  <div v-html="renderMarkdown(skillDetail.readme_md)" />
                </div>
                <span v-else class="text-sm text-[#9ca3af]">暂无 README 内容</span>
              </div>

              <!-- 右侧：元信息 + 操作 -->
              <div class="flex-shrink-0 lg:w-[300px] flex flex-col gap-4 px-5 py-4 border-t lg:border-t-0 border-[#e5e7eb]">
                <!-- 元信息卡片 -->
                <div class="rounded-xl border border-[#e5e7eb] bg-transparent p-4 space-y-3">
                  <div class="grid grid-cols-[60px_1fr] gap-x-3 gap-y-1.5 text-xs">
                    <span class="text-[#9ca3af]">版本</span>
                    <span class="text-[#1f2937] font-medium truncate">{{ skillDetail.latest_version?.version || skillDetail.version || '—' }}</span>
                    <span class="text-[#9ca3af]">作者</span>
                    <span class="text-[#1f2937] truncate">{{ skillDetail.owner_username || skillDetail.owner_uuid?.slice(0, 8) }}</span>
                    <span class="text-[#9ca3af]">大小</span>
                    <span class="text-[#1f2937]">{{ formatBytes(skillDetail.size_bytes) }}</span>
                    <span class="text-[#9ca3af]">下载</span>
                    <span class="text-[#1f2937] tabular-nums">{{ skillDetail.downloads }}</span>
                    <span class="text-[#9ca3af]">发布</span>
                    <span class="text-[#1f2937] truncate">{{ formatDate(skillDetail.created_at) }}</span>
                    <span class="text-[#9ca3af]">更新</span>
                    <span class="text-[#1f2937]">{{ formatDate(skillDetail.updated_at) }}</span>
                  </div>

                  <!-- 标签 -->
                  <div v-if="parseTags(skillDetail.tags).length > 0" class="flex flex-wrap gap-1.5 pt-1 border-t border-[#e5e7eb]">
                    <span
                      v-for="tag in parseTags(skillDetail.tags)"
                      :key="tag"
                      class="rounded-md bg-white px-2 py-0.5 text-xs text-[#6b7280] border border-[#e5e7eb]"
                    >
                      {{ tag }}
                    </span>
                  </div>

                  <!-- 贡献者 -->
                  <div
                    v-if="skillDetail.contributors && skillDetail.contributors.length > 0"
                    class="pt-1 border-t border-[#e5e7eb]"
                  >
                    <div class="text-[10px] text-[#9ca3af] mb-1.5">贡献者</div>
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="c in skillDetail.contributors"
                        :key="c.user_uuid"
                        class="rounded-md bg-white px-2 py-0.5 text-xs text-[#4b5563] border border-[#e5e7eb]"
                      >
                        {{ c.username || c.user_uuid.slice(0, 8) }}
                      </span>
                    </div>
                  </div>
                </div>

                <!-- 操作按钮 -->
                <div class="space-y-2">
                  <!-- 点赞 -->
                  <button
                    type="button"
                    class="flex h-10 w-full items-center justify-center gap-2 rounded-xl border text-sm font-medium transition-all duration-200 active:scale-[0.98]"
                    :class="skillDetail.liked_by_me
                      ? 'border-[#dc2626] bg-[#fef2f2] text-[#dc2626] hover:bg-[#fee2e2]'
                      : 'border-[#d1d5db] bg-white text-[#4b5563] hover:bg-[#f3f4f6]'"
                    @click="toggleSkillLike"
                  >
                    <svg class="h-4 w-4" :fill="skillDetail.liked_by_me ? 'currentColor' : 'none'" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    <span>{{ skillDetail.liked_by_me ? '已点赞' : '点赞' }} ({{ skillDetail.likes }})</span>
                  </button>

                  <!-- 安装到我的技能 -->
                  <button
                    type="button"
                    class="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[#1f2937] text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="installing"
                    @click="doInstall('user')"
                  >
                    {{ installing ? '安装中...' : '📥 安装到我的技能' }}
                  </button>

                  <!-- 安装到项目 -->
                  <div class="flex gap-2">
                    <select
                      v-model="selectedProjectId"
                      class="h-10 flex-1 rounded-xl border border-[#d1d5db] bg-white px-3 text-sm text-[#374151] outline-none focus:ring-2 focus:ring-[#1f2937]/20"
                    >
                      <option value="">选择项目</option>
                      <option v-for="p in projects" :key="p.pid" :value="p.pid">
                        {{ p.projectname }}
                      </option>
                    </select>
                    <button
                      type="button"
                      class="h-10 flex-shrink-0 rounded-xl bg-[#f3f4f6] px-4 text-sm font-semibold text-[#374151] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="installingProject || !selectedProjectId"
                      @click="doInstall('project')"
                    >
                      {{ installingProject ? '...' : '安装到项目' }}
                    </button>
                  </div>

                  <!-- 安装成功消息 -->
                  <p
                    v-if="installMsg"
                    class="rounded-lg bg-[#f0fdf4] px-3 py-2 text-xs text-[#166534]"
                  >
                    {{ installMsg }}
                  </p>

                  <!-- 作者操作：删除 -->
                  <button
                    v-if="isAuthor"
                    type="button"
                    class="flex h-9 w-full items-center justify-center gap-2 rounded-xl border border-[#efb3a7] bg-white text-sm text-[#b91c1c] transition-all duration-200 hover:bg-[#fee2e2] active:scale-[0.98] disabled:opacity-50"
                    :disabled="deleting"
                    @click="doDelete"
                  >
                    {{ deleting ? '删除中...' : '删除发布' }}
                  </button>
                </div>
              </div>
            </div>

            <!-- ═══ 评论区 ═══ -->
            <div class="border-t border-[#e5e7eb] px-5 py-4">
              <div class="mb-3 flex items-center justify-between">
                <span class="text-sm font-semibold text-[#1f2937]">
                  评论 ({{ totalCommentCount }})
                </span>
                <button
                  type="button"
                  class="text-xs text-[#6b7280] hover:text-[#1f2937] transition-colors"
                  @click="loadComments"
                >
                  刷新
                </button>
              </div>

              <!-- 评论输入框 -->
              <div class="mb-4 flex gap-2">
                <textarea
                  v-model="commentContent"
                  class="min-h-[44px] flex-1 resize-none rounded-xl border border-[#d1d5db] bg-white px-3.5 py-2.5 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                  placeholder="写下你的评论..."
                  rows="2"
                  :disabled="commentSubmitting"
                />
                <button
                  type="button"
                  class="flex h-10 flex-shrink-0 items-center justify-center rounded-xl bg-[#1f2937] px-5 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:border disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
                  :disabled="commentSubmitting || !commentContent.trim()"
                  @click="submitComment"
                >
                  {{ commentSubmitting ? '...' : '发送' }}
                </button>
              </div>

              <!-- 加载态 -->
              <div v-if="commentsLoading" class="py-8 text-center text-sm text-[#9ca3af]">
                加载评论中...
              </div>

              <!-- 空评论 -->
              <div v-else-if="comments.length === 0" class="py-8 text-center text-sm text-[#9ca3af]">
                暂无评论，来说两句吧
              </div>

              <!-- 评论列表 -->
              <div v-else class="space-y-4">
                <div
                  v-for="comment in comments"
                  :key="comment.id"
                  class="rounded-xl border border-[#e5e7eb] bg-transparent p-3.5"
                >
                  <!-- 顶级评论 -->
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="mb-1 flex items-center gap-2 text-xs">
                        <span class="font-semibold text-[#1f2937]">{{ comment.username || comment.user_uuid?.slice(0, 8) }}</span>
                        <span class="text-[#9ca3af]">{{ formatDate(comment.created_at) }}</span>
                      </div>
                      <p class="text-sm text-[#374151] whitespace-pre-wrap break-words">{{ comment.content }}</p>
                    </div>
                  </div>

                  <!-- 操作行 -->
                  <div class="mt-2 flex items-center gap-3 text-xs">
                    <button
                      type="button"
                      class="flex items-center gap-1 text-[#9ca3af] hover:text-[#dc2626] transition-colors"
                      :class="{ 'text-[#dc2626]': comment.liked_by_me }"
                      @click="toggleCommentLike(comment)"
                    >
                      <svg class="h-3.5 w-3.5" :fill="comment.liked_by_me ? 'currentColor' : 'none'" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                      </svg>
                      <span>{{ comment.likes || '' }}</span>
                    </button>
                    <button
                      type="button"
                      class="text-[#9ca3af] hover:text-[#1f2937] transition-colors"
                      @click="replyingTo = replyingTo === comment.id ? null : comment.id; replyContent = ''"
                    >
                      {{ replyingTo === comment.id ? '取消回复' : '回复' }}
                    </button>
                    <button
                      v-if="comment.user_uuid === currentUserId"
                      type="button"
                      class="text-[#9ca3af] hover:text-[#b91c1c] transition-colors"
                      @click="doDeleteComment(comment)"
                    >
                      删除
                    </button>
                    <button
                      type="button"
                      class="text-[#9ca3af] hover:text-[#efb3a7] transition-colors"
                      @click="openReport(comment)"
                    >
                      举报
                    </button>
                  </div>

                  <!-- 子回复列表 -->
                  <div
                    v-if="comment.replies && comment.replies.length > 0"
                    class="mt-3 space-y-2.5 border-l-2 border-[#f3f4f6] pl-4"
                  >
                    <div
                      v-for="reply in comment.replies"
                      :key="reply.id"
                      class="rounded-lg bg-[#f3f4f6]/40 p-3"
                    >
                      <div class="mb-1 flex items-center gap-2 text-xs">
                        <span class="font-semibold text-[#1f2937]">{{ reply.username || reply.user_uuid?.slice(0, 8) }}</span>
                        <span
                          v-if="reply.reply_to_username"
                          class="text-[#6b7280]"
                        >
                          回复 @{{ reply.reply_to_username }}
                        </span>
                        <span class="text-[#9ca3af]">{{ formatDate(reply.created_at) }}</span>
                      </div>
                      <p class="text-sm text-[#374151] whitespace-pre-wrap break-words">{{ reply.content }}</p>
                      <div class="mt-2 flex items-center gap-3 text-xs">
                        <button
                          type="button"
                          class="flex items-center gap-1 text-[#9ca3af] hover:text-[#dc2626] transition-colors"
                          :class="{ 'text-[#dc2626]': reply.liked_by_me }"
                          @click="toggleCommentLike(reply)"
                        >
                          <svg class="h-3.5 w-3.5" :fill="reply.liked_by_me ? 'currentColor' : 'none'" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                          </svg>
                          <span>{{ reply.likes || '' }}</span>
                        </button>
                        <button
                          v-if="reply.user_uuid === currentUserId"
                          type="button"
                          class="text-[#9ca3af] hover:text-[#b91c1c] transition-colors"
                          @click="doDeleteComment(reply)"
                        >
                          删除
                        </button>
                        <button
                          type="button"
                          class="text-[#9ca3af] hover:text-[#efb3a7] transition-colors"
                          @click="openReport(reply)"
                        >
                          举报
                        </button>
                      </div>
                    </div>
                  </div>

                  <!-- 内联回复输入框 -->
                  <div v-if="replyingTo === comment.id" class="mt-3 flex gap-2">
                    <textarea
                      v-model="replyContent"
                      class="min-h-[40px] flex-1 resize-none rounded-lg border border-[#d1d5db] bg-white px-3 py-2 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                      :placeholder="`回复 @${comment.username || '...'}...`"
                      rows="2"
                      :disabled="replySubmitting"
                    />
                    <button
                      type="button"
                      class="flex h-9 flex-shrink-0 items-center justify-center rounded-lg bg-[#1f2937] px-4 text-xs font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="replySubmitting || !replyContent.trim()"
                      @click="submitReply(comment.id, comment.user_uuid)"
                    >
                      {{ replySubmitting ? '...' : '回复' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </div>

    <!-- ═══ 举报弹窗 ═══ -->
    <Transition name="dialog-fade" appear>
      <div
        v-if="reportTarget"
        class="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 backdrop-blur-sm"
        @click.self="closeReport"
      >
        <div class="modal-card font-hans w-[400px] max-w-[95vw] rounded-2xl bg-white shadow-xl">
          <div class="flex h-12 flex-shrink-0 items-center justify-between px-5 bg-[#f9fafb] rounded-t-2xl border-b border-[#e5e7eb]">
            <span class="font-semibold text-[#1f2937] text-sm">举报评论</span>
            <button
              type="button"
              class="flex h-7 w-7 items-center justify-center rounded-full text-[#6b7280] transition-all duration-200 hover:bg-[#e5e7eb] hover:text-[#1f2937] active:scale-90"
              @click="closeReport"
            >
              <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="px-5 py-4 space-y-3">
            <p class="text-xs text-[#6b7280]">
              举报用户 <span class="font-semibold text-[#1f2937]">{{ reportTarget.username || reportTarget.user_uuid?.slice(0, 8) }}</span> 的评论
            </p>
            <select
              v-model="reportReason"
              class="h-10 w-full rounded-xl border border-[#d1d5db] bg-white px-3 text-sm text-[#374151] outline-none focus:ring-2 focus:ring-[#1f2937]/20"
            >
              <option value="">选择举报原因</option>
              <option value="spam">垃圾广告</option>
              <option value="harassment">骚扰言论</option>
              <option value="inappropriate">不当内容</option>
              <option value="other">其他</option>
            </select>
            <textarea
              v-model="reportDetail"
              class="min-h-[60px] w-full resize-none rounded-xl border border-[#d1d5db] bg-white px-3.5 py-2.5 text-sm text-[#1f2937] placeholder:text-[#9ca3af] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
              placeholder="详细说明（可选）"
              rows="2"
            />
          </div>

          <div class="flex justify-end gap-2 px-5 py-3 bg-[#f9fafb] rounded-b-2xl border-t border-[#e5e7eb]">
            <button
              type="button"
              class="h-9 rounded-xl border border-[#d1d5db] bg-white px-4 text-sm text-[#6b7280] transition-all duration-200 hover:bg-[#f3f4f6] active:scale-95"
              @click="closeReport"
            >
              取消
            </button>
            <button
              type="button"
              class="h-9 rounded-xl bg-[#1f2937] px-4 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="reportSubmitting || !reportReason"
              @click="submitReport"
            >
              {{ reportSubmitting ? '提交中...' : '提交举报' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
