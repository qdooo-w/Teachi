<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MessageContent from './components/MessageContent.vue'
import SkillManagerDialog from './components/SkillManagerDialog.vue'
import SkillPicker from './components/SkillPicker.vue'
import SkillChips from './components/SkillChips.vue'
import RowMenu from './components/RowMenu.vue'
import RenameInline from './components/RenameInline.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import { useRouter } from 'vue-router'
import {
  createSession,
  deleteProject,
  deleteSession,
  getCurrentUserId,
  getErrorMessage,
  listDisplayMessages,
  listSessions,
  renameProject,
  renameSession,
  sendChatMessage,
  stopChatGeneration,
  type DisplayMessage,
  type ProjectItem,
  type SessionItem,
} from './api'
import { listSkills, type FileSpace, type SkillMeta } from './skills'
import { useAuth } from './composables/useAuth'
import { useProjects } from './composables/useProjects'
import { useLayout } from './composables/useLayout'

// ── 认证（状态 / 行为均来自 composable，模板继续使用同名 ref） ───────────────
const {
  token,
  bootstrapping,
  preparing,
  authSubmitting,
  authError,
  errorMessage,
  authMode,
  authForm,
  initializeAuth,
  submitAuth,
  handleLogout: authLogout,
  handleTokenChange,
  setOnTokenReady,
  displayUser: displayUserFn,
} = useAuth()

// ── 视图与导航 ────────────────────────────────────────────────────────────────
type View = 'overview' | 'subject' | 'chat'
const currentView = ref<View>('overview')

const router = useRouter()

const { projects, loadProjects, resetProjects, upsertProject, removeProject } = useProjects()
const { sidebarOpen, isMobile, handleResize, closeSidebarOnMobile } = useLayout()
const sessions = ref<SessionItem[]>([])
const currentProject = ref<ProjectItem | null>(null)
const currentSession = ref<SessionItem | null>(null)

const newSessionDraft = ref('')
const creatingSession = ref(false)

const previewProjects = computed(() => projects.value.slice(0, 10))

// ── 聊天状态 ─────────────────────────────────────────────────────────────────
const streaming = ref(false)
const toolStatus = ref('')
const draft = ref('')
const messages = ref<DisplayMessage[]>([])
const chatContainer = ref<HTMLElement | null>(null)
const currentAbort = ref<AbortController | null>(null)
const stickToBottom = ref(true)
const composerTextarea = ref<HTMLTextAreaElement | null>(null)
const copiedId = ref<string | null>(null)
let copyResetTimer: number | null = null

const isAuthenticated = computed(() => Boolean(token.value))
const isChatReady = computed(
  () => Boolean(isAuthenticated.value && currentProject.value && currentSession.value && !preparing.value),
)
const canSend = computed(() => Boolean(draft.value.trim() && isChatReady.value && !streaming.value))
const displayUser = computed(() => displayUserFn())
const avatarLetter = computed(() => (displayUser.value.slice(0, 1) || 'U').toUpperCase())

// ── 科目 / 会话管理（重命名 / 删除） ─────────────────────────────────────────
// openMenuKey / renamingKey 使用 'project:{pid}' / 'session:{sid}' 命名空间以区分同 id 冲突
const openMenuKey = ref<string | null>(null)
const renamingKey = ref<string | null>(null)
const renameSubmitting = ref(false)

type DeleteTarget =
  | { kind: 'project'; id: string; name: string }
  | { kind: 'session'; id: string; name: string }

const confirmDelete = ref<DeleteTarget | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

function projectKey(scope: 'sidebar' | 'card', pid: string): string {
  return `${scope}:project:${pid}`
}

function sessionKey(sid: string): string {
  return `session:${sid}`
}

function toggleMenu(key: string): void {
  openMenuKey.value = openMenuKey.value === key ? null : key
}

function closeMenu(): void {
  openMenuKey.value = null
}

function startRename(key: string): void {
  renamingKey.value = key
  openMenuKey.value = null
}

function cancelRename(): void {
  renamingKey.value = null
}

async function submitProjectRename(project: ProjectItem, nextName: string): Promise<void> {
  renameSubmitting.value = true
  errorMessage.value = ''
  try {
    const updated = await renameProject(project.pid, nextName)
    upsertProject(updated)
    if (currentProject.value?.pid === updated.pid) currentProject.value = updated
    renamingKey.value = null
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    renameSubmitting.value = false
  }
}

async function submitSessionRename(session: SessionItem, nextName: string): Promise<void> {
  renameSubmitting.value = true
  errorMessage.value = ''
  try {
    const updated = await renameSession(session.sid, nextName)
    sessions.value = sessions.value.map((item) => (item.sid === updated.sid ? updated : item))
    if (currentSession.value?.sid === updated.sid) currentSession.value = updated
    renamingKey.value = null
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    renameSubmitting.value = false
  }
}

function askDeleteProject(project: ProjectItem): void {
  openMenuKey.value = null
  deleteError.value = ''
  confirmDelete.value = { kind: 'project', id: project.pid, name: project.projectname }
}

function askDeleteSession(session: SessionItem): void {
  openMenuKey.value = null
  deleteError.value = ''
  confirmDelete.value = { kind: 'session', id: session.sid, name: session.sessionname }
}

function cancelDelete(): void {
  if (deleteSubmitting.value) return
  confirmDelete.value = null
  deleteError.value = ''
}

async function performDelete(): Promise<void> {
  const target = confirmDelete.value
  if (!target || deleteSubmitting.value) return

  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    if (target.kind === 'project') {
      await deleteProject(target.id)
      removeProject(target.id)
      if (currentProject.value?.pid === target.id) {
        currentAbort.value?.abort()
        currentProject.value = null
        currentSession.value = null
        messages.value = []
        sessions.value = []
        currentView.value = 'overview'
      }
    } else {
      await deleteSession(target.id)
      sessions.value = sessions.value.filter((item) => item.sid !== target.id)
      if (currentSession.value?.sid === target.id) {
        currentSession.value = null
        messages.value = []
        currentView.value = 'subject'
      }
    }
    confirmDelete.value = null
  } catch (error) {
    deleteError.value = getErrorMessage(error)
  } finally {
    deleteSubmitting.value = false
  }
}

const deleteDialogContent = computed(() => {
  const target = confirmDelete.value
  if (!target) return null
  if (target.kind === 'project') {
    return {
      title: '删除科目',
      message: `确定删除「${target.name}」？该科目下的所有会话和消息也会被一并删除，操作不可恢复。`,
    }
  }
  return {
    title: '删除会话',
    message: `确定删除「${target.name}」？会话内的消息会被一并删除，操作不可恢复。`,
  }
})

// ── Skill ────────────────────────────────────────────────────────────────────
const showUserSkillManager = ref(false)
const showProjectSkillManager = ref(false)
const projectSkills = ref<SkillMeta[]>([])
const selectedSkills = ref<SkillMeta[]>([])
const showSkillPicker = ref(false)

const projectSkillSpace = computed<FileSpace | null>(() => {
  const pid = currentProject.value?.pid
  return pid ? { kind: 'project', pid } : null
})
const userSkillSpace = computed<FileSpace | null>(() => {
  const userId = getCurrentUserId()
  return token.value && userId ? { kind: 'user', userId } : null
})

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function truncateText(str: string, len: number): string {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}

function formatDateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function scrollToBottom(force = false): void {
  if (force) stickToBottom.value = true
  nextTick(() => {
    const container = chatContainer.value
    if (!container) return
    if (!stickToBottom.value) return
    container.scrollTop = container.scrollHeight
  })
}

function isChatAtBottom(): boolean {
  const container = chatContainer.value
  if (!container) return true
  const threshold = 32
  return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold
}

function handleChatScroll(): void {
  stickToBottom.value = isChatAtBottom()
}

// 科目总览横向卡片条：把纵向滚轮转成横向滚动，并用 rAF 缓动贴近原生横滑手感
const overviewStripEl = ref<HTMLElement | null>(null)
let overviewScrollTarget = 0
let overviewScrollRaf = 0

function onOverviewWheel(event: WheelEvent): void {
  // 触控板横向滑动时 |deltaX| 更大，不干预
  if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return
  const el = overviewStripEl.value
  if (!el) return
  if (el.scrollWidth <= el.clientWidth) return
  event.preventDefault()

  // 归一化 deltaMode：0=PX，1=LINE，2=PAGE
  let delta = event.deltaY
  if (event.deltaMode === 1) delta *= 16
  else if (event.deltaMode === 2) delta *= el.clientWidth

  // rAF 未运行时以当前位置为基准启动；运行中则在目标上继续累加
  if (!overviewScrollRaf) overviewScrollTarget = el.scrollLeft
  const maxScroll = el.scrollWidth - el.clientWidth
  overviewScrollTarget = Math.max(0, Math.min(maxScroll, overviewScrollTarget + delta))

  if (!overviewScrollRaf) overviewScrollRaf = requestAnimationFrame(stepOverviewScroll)
}

function stepOverviewScroll(): void {
  const el = overviewStripEl.value
  if (!el) {
    overviewScrollRaf = 0
    return
  }
  const diff = overviewScrollTarget - el.scrollLeft
  if (Math.abs(diff) < 0.5) {
    el.scrollLeft = overviewScrollTarget
    overviewScrollRaf = 0
    return
  }
  // 缓动因子：每帧吸收约 18%，视觉上接近原生横滑的余波
  el.scrollLeft += diff * 0.18
  overviewScrollRaf = requestAnimationFrame(stepOverviewScroll)
}

watch(overviewStripEl, (el, prev) => {
  if (prev) prev.removeEventListener('wheel', onOverviewWheel)
  if (el) el.addEventListener('wheel', onOverviewWheel, { passive: false })
})

// ── 导航 ──────────────────────────────────────────────────────────────────────
function goToProjectDetail(): void {
  if (!currentProject.value) return
  currentSession.value = null
  messages.value = []
  currentView.value = 'subject'
  void loadSessions(currentProject.value.pid)
}

async function goToSession(session: SessionItem): Promise<void> {
  currentSession.value = session
  currentView.value = 'chat'
  if (isMobile.value) sidebarOpen.value = false
  try {
    await loadMessages()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  }
}

// ── 数据加载 ─────────────────────────────────────────────────────────────────
async function loadSessions(pid: string): Promise<void> {
  sessions.value = await listSessions(pid)
}

async function loadMessages(): Promise<void> {
  if (!currentSession.value) return
  messages.value = await listDisplayMessages(currentSession.value.sid)
  scrollToBottom(true)
}

async function handleLogout(): Promise<void> {
  await authLogout()
  currentAbort.value?.abort()
  currentProject.value = null
  currentSession.value = null
  resetProjects()
  sessions.value = []
  messages.value = []
  draft.value = ''
  newSessionDraft.value = ''
  toolStatus.value = ''
  errorMessage.value = ''
  streaming.value = false
  projectSkills.value = []
  selectedSkills.value = []
  showSkillPicker.value = false
  showUserSkillManager.value = false
  showProjectSkillManager.value = false
  openMenuKey.value = null
  renamingKey.value = null
  confirmDelete.value = null
  deleteError.value = ''
  currentView.value = 'overview'
}

// ── 创建会话 ─────────────────────────────────────────────────────────────────
// 从 subject 视图"输入首条消息 + 回车"创建新会话并立即发送
async function handleStartNewSessionFromSubject(): Promise<void> {
  const text = newSessionDraft.value.trim()
  if (!text || !currentProject.value || streaming.value || creatingSession.value) return

  creatingSession.value = true
  errorMessage.value = ''

  try {
    const title = text.length > 15 ? text.slice(0, 15) + '...' : text
    const session = await createSession(currentProject.value.pid, title)
    sessions.value = [session, ...sessions.value]
    currentSession.value = session
    messages.value = []
    currentView.value = 'chat'
    newSessionDraft.value = ''
    draft.value = text
    await nextTick()
    await sendMessage()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    creatingSession.value = false
  }
}

// ── 聊天发送（保持原有逻辑） ────────────────────────────────────────────────
function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function updateMessage(id: string, patch: Partial<DisplayMessage>): void {
  const message = messages.value.find((item) => item.id === id)
  if (message) Object.assign(message, patch)
}

async function sendMessage(): Promise<void> {
  if (!canSend.value || !currentSession.value || !currentProject.value) return

  const rawContent = draft.value.trim()
  const content = buildPayload(rawContent, selectedSkills.value)
  const now = Date.now() / 1000
  const userMessage: DisplayMessage = {
    id: `local-user-${Date.now()}`,
    role: 'user',
    content: rawContent,
    timestamp: now,
  }
  const assistantId = `stream-assistant-${Date.now()}`
  const assistantMessage: DisplayMessage = {
    id: assistantId,
    role: 'assistant',
    content: '',
    timestamp: now,
    pending: true,
  }

  draft.value = ''
  selectedSkills.value = []
  errorMessage.value = ''
  toolStatus.value = ''
  messages.value.push(userMessage, assistantMessage)
  streaming.value = true

  const abortController = new AbortController()
  currentAbort.value = abortController
  scrollToBottom(true)

  try {
    const done = await sendChatMessage(
      currentSession.value.sid,
      currentProject.value.pid,
      content,
      {
        onTextDelta(delta) {
          const target = messages.value.find((message) => message.id === assistantId)
          if (target) target.content += delta
          scrollToBottom()
        },
        onToolEvent(event) {
          if (event.type === 'tool_call') {
            toolStatus.value = `正在调用 ${event.tool_name || '工具'}`
          }
          if (event.type === 'tool_result') {
            toolStatus.value = ''
          }
        },
      },
      abortController.signal,
    )

    updateMessage(assistantId, { pending: false })

    if (done.error) {
      updateMessage(assistantId, { content: messages.value.find((message) => message.id === assistantId)?.content || '生成失败。' })
      errorMessage.value = done.error_code ? `${done.error_code}: ${done.error}` : done.error
      return
    }

    if (done.msg_id) updateMessage(assistantId, { id: done.msg_id })
    await loadMessages()
  } catch (error) {
    updateMessage(assistantId, {
      pending: false,
      content: isAbortError(error)
        ? messages.value.find((message) => message.id === assistantId)?.content || '已停止生成。'
        : messages.value.find((message) => message.id === assistantId)?.content || '生成失败。',
    })
    if (!isAbortError(error)) errorMessage.value = getErrorMessage(error)
  } finally {
    streaming.value = false
    toolStatus.value = ''
    currentAbort.value = null
    scrollToBottom()
  }
}

async function stopStreaming(): Promise<void> {
  if (!streaming.value || !currentSession.value || !currentProject.value) return

  try {
    await stopChatGeneration(currentSession.value.sid, currentProject.value.pid)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    currentAbort.value?.abort()
  }
}

function handleComposerKeydown(event: KeyboardEvent): void {
  if (showSkillPicker.value && (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === 'Escape')) {
    // 方向键/Enter/Esc 由 SkillPicker 处理
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void sendMessage()
  }
}

// ── Skill 交互 ──────────────────────────────────────────────────────────────
async function loadProjectSkills(): Promise<void> {
  const space = projectSkillSpace.value
  if (!space) {
    projectSkills.value = []
    return
  }
  try {
    projectSkills.value = await listSkills(space)
  } catch {
    projectSkills.value = []
  }
}

function toggleSkill(name: string): void {
  const skill = projectSkills.value.find((s) => s.name === name)
  if (!skill) return
  const idx = selectedSkills.value.findIndex((s) => s.name === name)
  if (idx === -1) {
    selectedSkills.value.push(skill)
  } else {
    selectedSkills.value.splice(idx, 1)
  }
}

function removeSkill(name: string): void {
  selectedSkills.value = selectedSkills.value.filter((s) => s.name !== name)
}

function checkAtTrigger(): void {
  const el = composerTextarea.value
  if (!el) return
  const pos = el.selectionStart ?? 0
  const before = el.value.slice(0, pos)
  const match = before.match(/(^|[\s\n])@([a-z0-9-]*)$/)
  showSkillPicker.value = Boolean(match)
}

function handleComposerInput(): void {
  checkAtTrigger()
}

// ── Skill Picker 抽屉高度动画 hooks ──────────────────────────────────────────
function onDrawerBeforeEnter(el: Element): void {
  const node = el as HTMLElement
  node.style.height = '0'
}

function onDrawerEnter(el: Element, done: () => void): void {
  const node = el as HTMLElement
  const target = node.scrollHeight
  // 强制 reflow，保证从 height:0 过渡到目标高度
  void node.offsetHeight
  node.style.height = `${target}px`
  const handle = (): void => {
    node.removeEventListener('transitionend', handle)
    done()
  }
  node.addEventListener('transitionend', handle)
}

function onDrawerAfterEnter(el: Element): void {
  // 展开后让内容自适应（输入变长、筛选变化都可自由伸展）
  const node = el as HTMLElement
  node.style.height = ''
}

function onDrawerBeforeLeave(el: Element): void {
  const node = el as HTMLElement
  node.style.height = `${node.scrollHeight}px`
}

function onDrawerLeave(el: Element, done: () => void): void {
  const node = el as HTMLElement
  // 同样强制 reflow 再降为 0
  void node.offsetHeight
  node.style.height = '0'
  const handle = (): void => {
    node.removeEventListener('transitionend', handle)
    done()
  }
  node.addEventListener('transitionend', handle)
}

function handlePickerToggle(name: string): void {
  toggleSkill(name)
  const el = composerTextarea.value
  if (el) {
    const pos = el.selectionStart ?? 0
    const before = el.value.slice(0, pos)
    const cleaned = before.replace(/(^|[\s\n])@([a-z0-9-]*)$/, '$1')
    if (cleaned !== before) {
      el.value = cleaned + el.value.slice(pos)
      draft.value = el.value
      el.setSelectionRange(cleaned.length, cleaned.length)
    }
  }
}

function buildPayload(text: string, skills: SkillMeta[]): string {
  if (skills.length === 0) return text
  // 后端会为三层技能名各自加前缀（global- / project- / user-）再喂给模型。
  // 这里的选择器只展示项目层技能，因此发送时对应拼 project- 前缀，
  // 保证自然语言提示里的名字和模型 <skill> 列表、load_skill 参数一致。
  const names = skills.map((s) => `project-${s.name}`).join('、')
  return `[本轮请优先考虑使用技能：${names}]\n\n${text}`
}

async function copyMessage(id: string, content: string): Promise<void> {
  let ok = false
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(content)
      ok = true
    } catch { /* fall through */ }
  }
  if (!ok) {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = content
      textarea.setAttribute('readonly', '')
      textarea.style.cssText = 'position:fixed;opacity:0'
      document.body.appendChild(textarea)
      textarea.select()
      ok = document.execCommand('copy')
      document.body.removeChild(textarea)
    } catch { /* ignore */ }
  }
  if (ok) {
    copiedId.value = id
    if (copyResetTimer) window.clearTimeout(copyResetTimer)
    copyResetTimer = window.setTimeout(() => { copiedId.value = null }, 1500)
  }
}

function autosizeComposer(): void {
  const el = composerTextarea.value
  if (!el) return
  el.style.height = 'auto'
  const next = Math.min(el.scrollHeight, 240)
  el.style.height = `${next}px`
}

watch(draft, () => {
  nextTick(autosizeComposer)
})

// 进入 chat 视图后重新触发一次自适应
watch(currentView, (view) => {
  if (view === 'chat') nextTick(autosizeComposer)
})

// 项目切换时重载 skills 并清空已选
watch(currentProject, () => {
  void loadProjectSkills()
  selectedSkills.value = []
})

onMounted(() => {
  setOnTokenReady(async () => {
    preparing.value = true
    errorMessage.value = ''
    try {
      await loadProjects()
    } finally {
      preparing.value = false
    }
  })
  window.addEventListener('teachi-token-change', handleTokenChange)
  window.addEventListener('resize', handleResize)
  handleResize()
  void initializeAuth()
})

onBeforeUnmount(() => {
  window.removeEventListener('teachi-token-change', handleTokenChange)
  window.removeEventListener('resize', handleResize)
  currentAbort.value?.abort()
})
</script>

<template>
  <main class="h-full bg-[#f3f4f6] text-[#1f2937]">
    <!-- 登录 / 注册 -->
    <section v-if="bootstrapping || !isAuthenticated" class="flex h-full items-center justify-center px-4">
      <div class="w-full max-w-[420px] rounded-lg border border-[#d1d5db] bg-white p-6 shadow-sm">
        <div class="mb-6">
          <div class="text-2xl font-bold tracking-normal">Teachi</div>
          <div class="mt-1 text-sm text-[#6b7280]">
            {{ bootstrapping ? '正在连接后端...' : '登录后开始对话' }}
          </div>
        </div>

        <div v-if="bootstrapping" class="h-32 rounded-md border border-dashed border-[#d1d5db] bg-[#f9fafb]" />

        <form v-else class="space-y-4" @submit.prevent="submitAuth">
          <div class="grid grid-cols-2 rounded-md border border-[#d1d5db] bg-[#f9fafb] p-1">
            <button
              type="button"
              :class="[
                'h-9 rounded px-3 text-sm font-medium transition-colors',
                authMode === 'login' ? 'bg-white text-[#111827] shadow-sm' : 'text-[#6b7280] hover:text-[#111827]',
              ]"
              @click="authMode = 'login'"
            >
              登录
            </button>
            <button
              type="button"
              :class="[
                'h-9 rounded px-3 text-sm font-medium transition-colors',
                authMode === 'register' ? 'bg-white text-[#111827] shadow-sm' : 'text-[#6b7280] hover:text-[#111827]',
              ]"
              @click="authMode = 'register'"
            >
              注册
            </button>
          </div>

          <label v-if="authMode === 'register'" class="block">
            <span class="mb-1 block text-sm font-medium">用户名</span>
            <input
              v-model="authForm.username"
              class="h-11 w-full rounded-md border border-[#d1d5db] bg-white px-3 outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
              autocomplete="username"
              type="text"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">邮箱</span>
            <input
              v-model="authForm.email"
              class="h-11 w-full rounded-md border border-[#d1d5db] bg-white px-3 outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
              autocomplete="email"
              type="email"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-sm font-medium">密码</span>
            <input
              v-model="authForm.password"
              class="h-11 w-full rounded-md border border-[#d1d5db] bg-white px-3 outline-none transition focus:border-[#1f6f5b] focus:ring-2 focus:ring-[#1f6f5b]/20"
              autocomplete="current-password"
              type="password"
            />
          </label>

          <p v-if="authError" class="rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
            {{ authError }}
          </p>

          <button
            class="h-11 w-full rounded-md bg-[#1f2937] px-4 text-sm font-semibold text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#9ca3af]"
            :disabled="authSubmitting"
            type="submit"
          >
            {{ authSubmitting ? '处理中...' : authMode === 'login' ? '登录' : '创建账号' }}
          </button>
        </form>
      </div>
    </section>

    <!-- 主应用：侧边栏 + 工作区 -->
    <section v-else class="flex h-full w-full overflow-hidden">
      <!-- 移动端遮罩 -->
      <div
        v-if="sidebarOpen && isMobile"
        class="fixed inset-0 z-40 bg-black/20"
        @click="sidebarOpen = false"
      />

      <!-- 侧边栏 -->
      <aside
        :class="[
          'fixed z-50 flex h-full flex-col bg-white transition-all duration-300 md:relative',
          sidebarOpen
            ? 'w-64 translate-x-0 border-r border-[#d1d5db]'
            : '-translate-x-full overflow-hidden border-none md:w-0 md:translate-x-0',
        ]"
      >
        <div class="flex h-full w-64 flex-shrink-0 flex-col p-4">
          <button
            class="mb-6 mt-2 flex items-center gap-2 px-2 text-left"
            type="button"
            @click="closeSidebarOnMobile(); router.push({ name: 'overview' })"
          >
            <span class="text-xl font-bold tracking-tight">Teachi</span>
          </button>

          <div class="no-scrollbar flex-1 overflow-y-auto">
            <div class="mb-2 px-2 text-xs font-medium text-[#6b7280]">我的科目</div>
            <div class="flex flex-col gap-1">
              <div
                v-for="project in previewProjects"
                :key="project.pid"
                class="group relative"
              >
                <RenameInline
                  v-if="renamingKey === projectKey('sidebar', project.pid)"
                  :initial="project.projectname"
                  :submitting="renameSubmitting"
                  placeholder="新科目名称"
                  @submit="(name) => submitProjectRename(project, name)"
                  @cancel="cancelRename"
                />
                <div
                  v-else
                  role="button"
                  tabindex="0"
                  :class="[
                    'flex min-h-[40px] w-full cursor-pointer items-center justify-start gap-2 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                    currentProject?.pid === project.pid
                      ? 'border-[#d1d5db] bg-[#e5e7eb] font-medium'
                      : 'border-transparent hover:border-[#d1d5db] hover:bg-[#e5e7eb]',
                  ]"
                  @click="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: project.pid } })"
                  @keydown.enter.prevent="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: project.pid } })"
                >
                  <svg class="h-4 w-4 flex-shrink-0 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  <span class="flex-1 truncate text-sm">{{ project.projectname }}</span>
                  <RowMenu
                    :open="openMenuKey === projectKey('sidebar', project.pid)"
                    class="opacity-0 transition-opacity group-hover:opacity-100"
                    :class="{ '!opacity-100': openMenuKey === projectKey('sidebar', project.pid) }"
                    @toggle="toggleMenu(projectKey('sidebar', project.pid))"
                    @close="closeMenu"
                    @rename="startRename(projectKey('sidebar', project.pid))"
                    @delete="askDeleteProject(project)"
                  />
                </div>
              </div>
              <button
                type="button"
                class="flex min-h-[40px] w-full items-center justify-start gap-2 rounded-lg border border-dashed border-[#d1d5db] px-3 py-2.5 text-left text-sm text-[#6b7280] transition-colors hover:border-solid hover:bg-[#e5e7eb]"
                @click="closeSidebarOnMobile(); router.push({ name: 'overview' })"
              >
                查看全部科目
              </button>
            </div>
          </div>

          <div class="mt-4 flex-shrink-0 space-y-1 border-t border-[#d1d5db] pt-4">
            <button
              class="flex min-h-[40px] w-full cursor-not-allowed items-center justify-start gap-2 rounded-lg border border-transparent px-3 py-2.5 text-left text-sm text-[#9ca3af]"
              type="button"
              disabled
              title="暂未实现"
            >
              <svg class="h-4 w-4 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              文档
            </button>
            <button
              class="flex min-h-[40px] w-full cursor-not-allowed items-center justify-start gap-2 rounded-lg border border-transparent px-3 py-2.5 text-left text-sm text-[#9ca3af]"
              type="button"
              disabled
              title="暂未实现"
            >
              <svg class="h-4 w-4 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              仪表盘
            </button>
            <button
              class="flex min-h-[40px] w-full cursor-not-allowed items-center justify-start gap-2 rounded-lg border border-transparent px-3 py-2.5 text-left text-sm text-[#9ca3af]"
              type="button"
              disabled
              title="暂未实现"
            >
              <svg class="h-4 w-4 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              设置
            </button>
            <div
              class="mt-2 flex cursor-pointer items-center gap-3 rounded-xl border-t border-[#d1d5db] px-3 pb-2 pt-3 transition-colors hover:bg-[#e5e7eb]"
              title="退出登录"
              @click="handleLogout"
            >
              <div class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-[#d1d5db] text-sm">
                {{ avatarLetter }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium">{{ displayUser }}</div>
                <div class="truncate text-xs text-[#6b7280]">点击退出登录</div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 主内容区 -->
      <section class="relative flex min-w-0 flex-1 flex-col bg-[#f3f4f6] transition-all duration-300">
        <header class="flex h-14 flex-shrink-0 items-center justify-between px-4">
          <div class="flex min-w-0 items-center gap-3 overflow-hidden">
            <button
              class="flex-shrink-0 rounded-xl p-2 text-[#4b5563] transition-colors hover:bg-[#e5e7eb]"
              type="button"
              title="切换侧边栏"
              @click="sidebarOpen = !sidebarOpen"
            >
              <svg class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div class="flex items-center gap-2 truncate text-sm font-medium text-[#4b5563]">
              <template v-if="currentView === 'overview'">
                <span class="text-[#1f2937]">科目总览</span>
                <span v-if="preparing" class="text-xs text-[#9ca3af]">准备中</span>
              </template>
              <template v-else-if="currentView === 'subject' && currentProject">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="router.push({ name: 'overview' })">科目</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(currentProject.projectname, 20) }}</span>
              </template>
              <template v-else-if="currentView === 'chat' && currentProject && currentSession">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="goToProjectDetail">{{ truncateText(currentProject.projectname, 8) }}</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(currentSession.sessionname, 15) }}</span>
              </template>
            </div>
          </div>

          <div class="flex items-center gap-1">
            <button
              v-if="currentView === 'chat'"
              class="flex h-9 items-center gap-1 rounded-xl border border-transparent px-3 text-sm text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="新建对话"
              @click="goToProjectDetail"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              <span class="hidden sm:inline">新建对话</span>
            </button>
            <button
              v-if="currentView === 'chat'"
              class="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="刷新消息"
              @click="loadMessages"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M20 9a8 8 0 0 0-14.9-4M4 15a8 8 0 0 0 14.9 4" />
              </svg>
            </button>
            <button
              class="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="我的技能"
              @click="showUserSkillManager = true"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7z" />
              </svg>
            </button>
            <button
              v-if="currentProject"
              class="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="项目技能"
              @click="showProjectSkillManager = true"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
              </svg>
            </button>
          </div>
        </header>

        <div class="relative flex-1 overflow-hidden">
          <!-- 1. 科目总览 -->
          <RouterView v-slot="{ Component }">
            <component :is="Component" v-if="$route.name === 'overview'" />
          </RouterView>

          <!-- 2. 科目概览（会话列表） -->
          <div v-if="currentView === 'subject' && currentProject" class="absolute inset-0 flex flex-col overflow-y-auto px-4 py-5 md:px-6">
            <div class="mx-auto flex w-full max-w-3xl flex-1 flex-col">
              <div class="mb-8">
                <h2 class="mb-2 text-3xl font-bold">{{ currentProject.projectname }}</h2>
                <p class="text-sm text-[#6b7280]">创建于 {{ formatDate(currentProject.created_at) }}</p>
              </div>
              <div class="mb-4 border-b border-[#d1d5db] pb-2 text-sm font-medium text-[#6b7280]">历史会话</div>
              <div class="no-scrollbar mb-6 flex-1 space-y-3 overflow-y-auto">
                <div v-for="session in sessions" :key="session.sid">
                  <div
                    v-if="renamingKey === sessionKey(session.sid)"
                    class="rounded-2xl bg-white p-4 shadow-sm"
                  >
                    <div class="mb-2 text-xs text-[#6b7280]">重命名会话</div>
                    <RenameInline
                      :initial="session.sessionname"
                      :submitting="renameSubmitting"
                      placeholder="新会话名称"
                      @submit="(name) => submitSessionRename(session, name)"
                      @cancel="cancelRename"
                    />
                  </div>
                  <div
                    v-else
                    role="button"
                    tabindex="0"
                    class="group flex w-full cursor-pointer items-center justify-between rounded-2xl bg-white p-4 text-left shadow-sm transition-colors hover:bg-[#f9fafb]"
                    @click="goToSession(session)"
                    @keydown.enter.prevent="goToSession(session)"
                  >
                    <div class="min-w-0 flex-1 pr-4">
                      <div class="truncate font-medium text-[#1f2937]">{{ session.sessionname }}</div>
                      <div class="mt-1 truncate text-xs text-[#9ca3af]">更新于 {{ formatDateTime(session.timestamp) }}</div>
                    </div>
                    <RowMenu
                      :open="openMenuKey === sessionKey(session.sid)"
                      :disable-delete="streaming && currentSession?.sid === session.sid"
                      delete-disabled-reason="生成中不能删除"
                      @toggle="toggleMenu(sessionKey(session.sid))"
                      @close="closeMenu"
                      @rename="startRename(sessionKey(session.sid))"
                      @delete="askDeleteSession(session)"
                    />
                  </div>
                </div>
                <div v-if="sessions.length === 0" class="rounded-2xl bg-white py-10 text-center text-[#9ca3af] shadow-sm">
                  暂无会话，在下方输入以开始。
                </div>
              </div>
              <div class="mt-auto w-full pb-2">
                <p v-if="errorMessage" class="mb-2 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
                  {{ errorMessage }}
                </p>
                <div class="relative flex flex-col gap-2 rounded-3xl bg-white p-3 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-[#1f6f5b]/20">
                  <textarea
                    v-model="newSessionDraft"
                    class="max-h-32 w-full resize-none overflow-y-auto border-none bg-transparent leading-normal text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
                    placeholder="在这个科目中新建会话... (Enter 发送)"
                    rows="1"
                    :disabled="creatingSession || streaming"
                    @keydown.enter.prevent="handleStartNewSessionFromSubject"
                  />
                  <div class="flex items-center justify-end">
                    <button
                      type="button"
                      class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
                      :disabled="!newSessionDraft.trim() || creatingSession || streaming"
                      title="创建会话并发送"
                      @click="handleStartNewSessionFromSubject"
                    >
                      <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14m0 0-6-6m6 6-6 6" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 3. 具体对话 -->
          <div v-if="currentView === 'chat' && currentSession" class="absolute inset-0 flex flex-col">
            <div ref="chatContainer" class="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6" @scroll.passive="handleChatScroll">
              <div class="mx-auto flex max-w-3xl flex-col gap-5 pb-4">
                <div v-if="messages.length === 0" class="mt-16 rounded-lg border border-dashed border-[#d1d5db] bg-white px-4 py-8 text-center text-sm text-[#6b7280]">
                  还没有消息。
                </div>

                <div v-for="message in messages" :key="message.id" class="flex w-full flex-col">
                  <div v-if="message.role === 'user'" class="flex justify-end">
                    <div class="max-w-[85%] rounded-3xl border border-[#d1d5db] bg-[#e5e7eb] px-5 py-3 text-[15px] leading-relaxed text-[#1f2937]">
                      <p class="whitespace-pre-wrap break-words">{{ message.content }}</p>
                    </div>
                  </div>
                  <div v-else class="group flex max-w-[85%] flex-col items-start">
                    <div class="rounded-3xl bg-white px-5 py-4 text-[15px] leading-relaxed text-[#1f2937]">
                      <MessageContent
                        v-if="message.content"
                        :content="message.content"
                        :streaming="message.pending === true"
                      />
                      <p v-else-if="!message.pending" class="whitespace-pre-wrap break-words text-[#6b7280]">（空响应）</p>
                      <div v-if="message.pending" class="mt-3 flex gap-1">
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280]" />
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280] [animation-delay:120ms]" />
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-[#6b7280] [animation-delay:240ms]" />
                      </div>
                    </div>
                    <button
                      v-if="message.content && !message.pending"
                      class="ml-2 mt-1 flex h-6 w-6 items-center justify-center rounded text-[#9ca3af] opacity-0 transition-opacity hover:bg-[#e5e7eb] hover:text-[#4b5563] group-hover:opacity-100"
                      :title="copiedId === message.id ? '已复制' : '复制'"
                      type="button"
                      @click="copyMessage(message.id, message.content)"
                    >
                      <svg v-if="copiedId !== message.id" class="h-3.5 w-3.5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2m-6 12h8a2 2 0 0 1 2-2v-8a2 2 0 0 1-2-2h-8a2 2 0 0 1-2 2v8a2 2 0 0 1 2 2z" />
                      </svg>
                      <svg v-else class="h-3.5 w-3.5 text-[#1f6f5b]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <footer class="flex-shrink-0 bg-[#f3f4f6] px-4 pb-3 pt-2">
              <div class="mx-auto max-w-3xl">
                <p v-if="errorMessage" class="mb-2 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
                  {{ errorMessage }}
                </p>
                <p v-if="toolStatus" class="mb-2 text-xs text-[#4b5563]">{{ toolStatus }}</p>

                <Transition
                  name="skill-drawer"
                  @before-enter="onDrawerBeforeEnter"
                  @enter="onDrawerEnter"
                  @after-enter="onDrawerAfterEnter"
                  @before-leave="onDrawerBeforeLeave"
                  @leave="onDrawerLeave"
                >
                  <SkillPicker
                    v-if="showSkillPicker"
                    :skills="projectSkills"
                    :selected="selectedSkills.map((s) => s.name)"
                    @toggle="handlePickerToggle"
                    @close="showSkillPicker = false"
                  />
                </Transition>
                <div
                  :class="[
                    'composer-shell relative bg-white p-3 shadow-sm focus-within:ring-2 focus-within:ring-[#1f6f5b]/20',
                    showSkillPicker ? 'drawer-open' : '',
                    streaming ? 'generating' : '',
                  ]"
                >
                  <SkillChips
                    v-if="selectedSkills.length > 0"
                    :skills="selectedSkills"
                    @remove="removeSkill"
                  />
                  <textarea
                    ref="composerTextarea"
                    v-model="draft"
                    class="composer-textarea w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-[#9ca3af]"
                    :disabled="streaming || preparing"
                    placeholder="给 Teachi 发送消息... (Enter 换行，Ctrl/⌘ + Enter 发送，@ 呼出技能选择)"
                    rows="2"
                    @keydown="handleComposerKeydown"
                    @input="handleComposerInput"
                    @click="checkAtTrigger"
                  />
                  <div class="mt-2 flex items-center justify-between">
                    <button
                      class="flex h-8 w-8 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="streaming || preparing"
                      title="添加技能"
                      type="button"
                      @click="showSkillPicker = !showSkillPicker"
                    >
                      <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
                      </svg>
                    </button>
                    <button
                      v-if="streaming"
                      class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-[#d1d5db] bg-white px-5 text-[#6b7280] transition hover:border-[#9ca3af] hover:text-[#1f2937]"
                      title="停止生成"
                      type="button"
                      @click="stopStreaming"
                    >
                      <svg class="h-4 w-4" aria-hidden="true" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M7 7h10v10H7z" />
                      </svg>
                    </button>
                    <button
                      v-else
                      class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
                      :disabled="!canSend"
                      title="发送"
                      type="button"
                      @click="sendMessage"
                    >
                      <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14m0 0-6-6m6 6-6 6" />
                      </svg>
                    </button>
                  </div>
                </div>
                <p class="mt-2 text-center text-[10px] text-[#9ca3af]">Teachi 可能会犯错。请核查重要信息。</p>
              </div>
            </footer>
          </div>
        </div>
      </section>
    </section>

    <SkillManagerDialog
      v-if="showUserSkillManager && userSkillSpace"
      :space="userSkillSpace"
      title="我的技能（用户级）"
      @close="showUserSkillManager = false"
    />
    <SkillManagerDialog
      v-if="showProjectSkillManager && projectSkillSpace"
      :space="projectSkillSpace"
      title="项目技能"
      @close="showProjectSkillManager = false; loadProjectSkills()"
    />
    <ConfirmDialog
      v-if="confirmDelete && deleteDialogContent"
      :title="deleteDialogContent.title"
      :message="deleteDialogContent.message"
      confirm-text="删除"
      danger
      :submitting="deleteSubmitting"
      :error="deleteError"
      @confirm="performDelete"
      @cancel="cancelDelete"
    />
  </main>
</template>
