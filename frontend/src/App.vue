<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SkillManagerDialog from './components/SkillManagerDialog.vue'
import ChatSkillSidebar from './components/ChatSkillSidebar.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import UserProfileDialog from './components/UserProfileDialog.vue'
import RowMenu from './components/RowMenu.vue'
import RenameInline from './components/RenameInline.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import { useRoute, useRouter } from 'vue-router'
import {
  deleteProject,
  getCurrentUserId,
  getErrorMessage,
  listSessions,
  renameProject,
  register,
  requestPasswordReset,
  type ProjectItem,
  type SessionItem,
} from './api'
import { type FileSpace } from './skills'
import { useAuth } from './composables/useAuth'
import { useProjects } from './composables/useProjects'
import { useLayout } from './composables/useLayout'
import { useProjectSkills } from './composables/useProjectSkills'
import { useUserSkills } from './composables/useUserSkills'
import { useChatSkillSidebar } from './composables/useChatSkillSidebar'
import { PREVIEW_PROJECT_LIMIT, API_BASE_URL } from './config'
import { useNotification } from './composables/useNotification'
import { confirmDanger, useConfirmDialog } from './composables/useConfirmDialog'

// ── 认证（状态 / 行为均来自 composable，模板继续使用同名 ref） ───────────────
const {
  token,
  currentUser,
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

// ── 全局悬浮通知 ───────────────────────────────────────────────────────────
const {
  notifications,
  showError: showGlobalError,
  removeNotification,
  clearAllNotifications,
  toggleNotificationExpanded,
} = useNotification()
const {
  confirmState,
  resolveConfirm,
  cancelConfirm,
} = useConfirmDialog()

// 监听旧的 errorMessage 变化以支持 legacy code
watch(errorMessage, (newVal) => {
  if (newVal) {
    showGlobalError(newVal)
    errorMessage.value = ''
  }
})

// 将登录/注册表单的内联 authError 转发到全局通知
watch(authError, (newVal) => {
  if (newVal) {
    showGlobalError(newVal)
    authError.value = ''
  }
})

// 当全局通知全部被清除时，同步清空 legacy errorMessage
watch(() => notifications.value.length, (newCount) => {
  if (newCount === 0) {
    errorMessage.value = ''
  }
})

async function handleSubmitAuth(): Promise<void> {
  authError.value = ''
  if (authMode.value === 'login') {
    await submitAuth()
  } else if (authMode.value === 'register') {
    if (!authForm.email.trim()) {
      authError.value = '请输入邮箱地址。'
      return
    }
    authSubmitting.value = true
    try {
      await register(authForm.email.trim())
      await router.push({
        name: 'register-confirm',
        query: { email: authForm.email.trim() },
      })
    } catch (error) {
      authError.value = getErrorMessage(error)
    } finally {
      authSubmitting.value = false
    }
  } else {
    // forgot
    if (!authForm.email.trim()) {
      authError.value = '请输入邮箱地址。'
      return
    }
    authSubmitting.value = true
    try {
      await requestPasswordReset(authForm.email.trim())
      await router.push({
        name: 'register-confirm',
        query: { email: authForm.email.trim(), is_reset: 'true' },
      })
    } catch (error) {
      authError.value = getErrorMessage(error)
    } finally {
      authSubmitting.value = false
    }
  }
}

// ── 路由 / 共享状态 ─────────────────────────────────────────────────────────
const router = useRouter()
const route = useRoute()

// ── 路由层级深度：overview/community/library=0，subject=1，chat=2 ──────────────────
const ROUTE_DEPTH: Record<string, number> = {
  overview: 0,
  community: 0,
  library: 0,
  subject: 1,
  chat: 2,
}

function getRouteDepth(name: string | null | undefined): number {
  return ROUTE_DEPTH[name ?? ''] ?? 0
}

// direction='forward' 表示向下导航（右进左出），'backward' 表示向上导航（左进右出）
const navDirection = ref<'forward' | 'backward'>('forward')

watch(route, (to, from) => {
  const toDepth = getRouteDepth(to.name as string)
  const fromDepth = getRouteDepth(from.name as string)
  navDirection.value = toDepth >= fromDepth ? 'forward' : 'backward'
})

const { projects, loadProjects, resetProjects, upsertProject, removeProject } = useProjects()
const { sidebarOpen, isMobile, handleResize, closeSidebarOnMobile } = useLayout()
const { chatSidebarOpen, editingSkill, toggleSidebar: toggleChatSidebar, closeEditor } = useChatSkillSidebar()

const LOGOUT_SESSION_STATE_KEYS = ['library-tabs', 'community-tabs']
const LOGOUT_LOCAL_STATE_KEYS = ['library-sidebar-open']
const LOGOUT_LOCAL_STATE_PREFIXES = ['preview_windows_', 'chat_cache_']

function removeLocalStorageByPrefix(prefix: string): void {
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index)
    if (key?.startsWith(prefix)) {
      localStorage.removeItem(key)
    }
  }
}

function clearLogoutUiStorage(): void {
  for (const key of LOGOUT_SESSION_STATE_KEYS) {
    sessionStorage.removeItem(key)
  }
  for (const key of LOGOUT_LOCAL_STATE_KEYS) {
    localStorage.removeItem(key)
  }
  for (const prefix of LOGOUT_LOCAL_STATE_PREFIXES) {
    removeLocalStorageByPrefix(prefix)
  }
}

// ── 全局捕获滚动，用于检测任何滚动区域是否向下滚动，控制顶栏半透明背景显隐 ───
const hasScrolled = ref(false)

function handleGlobalScroll(e: Event) {
  const target = e.target as HTMLElement
  if (target && target.scrollTop !== undefined) {
    hasScrolled.value = target.scrollTop > 8
  }
}

// 路由改变时重置滚动状态
watch(route, () => {
  hasScrolled.value = false
})

const previewProjects = computed(() => projects.value.slice(0, PREVIEW_PROJECT_LIMIT))

const subjectProject = computed(() => {
  const pid = route.params.pid as string | undefined
  return pid ? projects.value.find((p) => p.pid === pid) ?? null : null
})

// 聊天面包屑所需：同一套 pid 计算 + 由 route.params.sid 独立拉取一次 sessions
const chatProject = computed(() => {
  const pid = route.params.pid as string | undefined
  return pid ? projects.value.find((p) => p.pid === pid) ?? null : null
})
const chatSession = ref<SessionItem | null>(null)

watch(
  () => [route.name, route.params.pid, route.params.sid] as const,
  async ([name, pid, sid]) => {
    if (name !== 'chat' || !pid || !sid) {
      chatSession.value = null
      return
    }
    try {
      const sessions = await listSessions(pid as string)
      chatSession.value = sessions.find((s) => s.sid === sid) ?? null
    } catch {
      chatSession.value = null
    }
  },
  { immediate: true },
)

// ── 认证派生 ─────────────────────────────────────────────────────────────────
const isAuthenticated = computed(() => Boolean(token.value))
const displayUser = computed(() => displayUserFn())
const avatarLetter = computed(() => (displayUser.value.slice(0, 1) || 'U').toUpperCase())

// ── 侧栏科目管理（重命名 / 删除） ───────────────────────────────────────────
// openMenuKey / renamingKey 使用 'sidebar:project:{pid}' 命名空间
const openMenuKey = ref<string | null>(null)
const renamingKey = ref<string | null>(null)
const renameSubmitting = ref(false)

function projectKey(_scope: 'sidebar', pid: string): string {
  return `sidebar:project:${pid}`
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
    renamingKey.value = null
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    renameSubmitting.value = false
  }
}

async function askDeleteProject(project: ProjectItem): Promise<void> {
  openMenuKey.value = null
  const confirmed = await confirmDanger({
    title: '删除科目',
    message: `确定删除「${project.projectname}」？该科目下的所有会话和消息也会被一并删除，操作不可恢复。`,
    confirmText: '删除',
  })
  if (!confirmed) return
  try {
    await deleteProject(project.pid)
    // 如果正在查看被删除的项目或其会话，回到总览
    if (route.params.pid === project.pid) {
      await router.replace({ name: 'overview' })
    }
    removeProject(project.pid)
  } catch (error) {
    showGlobalError('删除科目失败', getErrorMessage(error))
  }
}

// ── Skill 管理对话框（用户级 / 项目级） ─────────────────────────────────────
const showUserSkillManager = ref(false)
const showProjectSkillManager = ref(false)
const showSettingsDialog = ref(false)

const currentPid = computed(() => (route.params.pid as string | undefined) ?? null)

const projectSkillSpace = computed<FileSpace | null>(() => {
  return currentPid.value ? { kind: 'project', pid: currentPid.value } : null
})
const userSkillSpace = computed<FileSpace | null>(() => {
  const userId = getCurrentUserId()
  return token.value && userId ? { kind: 'user', userId } : null
})

// 项目技能列表共享单例：ChatView 也通过它订阅；对话框关闭后 refresh() 一次
// 所有订阅者都会更新，不再需要 window 事件总线。
const { refresh: refreshProjectSkills } = useProjectSkills(currentPid)
const { refresh: refreshUserSkills } = useUserSkills()

async function closeProjectSkillManager(): Promise<void> {
  showProjectSkillManager.value = false
  // 对话框里可能有增删改，刷新缓存让所有订阅方同步
  await refreshProjectSkills()
}

async function closeUserSkillManager(): Promise<void> {
  showUserSkillManager.value = false
  // 对话框里可能有增删改，刷新缓存让所有订阅方同步
  await refreshUserSkills()
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function truncateText(str: string, len: number): string {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

// ── 登出 ─────────────────────────────────────────────────────────────────────
function resetOpenUiStateAfterLogout(): void {
  clearLogoutUiStorage()
  resetProjects()
  recentSessions.value = []
  chatSession.value = null
  errorMessage.value = ''
  sidebarOpen.value = !isMobile.value
  chatSidebarOpen.value = false
  closeEditor()
  showUserSkillManager.value = false
  showProjectSkillManager.value = false
  showSettingsDialog.value = false
  showUserProfileDialog.value = false
  openMenuKey.value = null
  renamingKey.value = null
  hasScrolled.value = false
  clearAllNotifications()
  cancelConfirm()
}

async function handleLogout(): Promise<void> {
  try {
    await authLogout()
  } catch (error) {
    console.warn('Logout request failed:', error)
  }
  resetOpenUiStateAfterLogout()
  await router.replace({ name: 'overview' })
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
function updateKeyboardOffset() {
  if (window.visualViewport) {
    const offset = isMobile.value ? Math.max(0, window.innerHeight - window.visualViewport.height) : 0
    document.documentElement.style.setProperty('--keyboard-offset', `${offset}px`)
  }
}

const showUserProfileDialog = ref(false)
const avatarVersion = ref(0)
const hasAvatarError = ref(false)

function handleAvatarError() {
  hasAvatarError.value = true
}

function handleAvatarUpdated() {
  avatarVersion.value++
  hasAvatarError.value = false
}

watch([avatarVersion, currentUser], () => {
  hasAvatarError.value = false
})

// 当页面大范围切换（路由变化）或打开各类弹窗时，自动清除所有提示框
watch(
  [
    () => route.path,
    showUserSkillManager,
    showProjectSkillManager,
    showSettingsDialog,
    showUserProfileDialog,
  ],
  () => {
    clearAllNotifications()
  }
)

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
  window.addEventListener('learnova-token-change', handleTokenChange)
  window.addEventListener('resize', handleResize)
  window.addEventListener('learnova-avatar-updated', handleAvatarUpdated)
  window.addEventListener('scroll', handleGlobalScroll, true) // 捕获局部滚动
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', updateKeyboardOffset)
    window.visualViewport.addEventListener('scroll', updateKeyboardOffset)
    updateKeyboardOffset()
  }
  handleResize()
  void initializeAuth()
})

onBeforeUnmount(() => {
  window.removeEventListener('learnova-token-change', handleTokenChange)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('learnova-avatar-updated', handleAvatarUpdated)
  window.removeEventListener('scroll', handleGlobalScroll, true)
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', updateKeyboardOffset)
    window.visualViewport.removeEventListener('scroll', updateKeyboardOffset)
  }
})

interface QuickAccessSession {
  sid: string
  sessionname: string
  timestamp: number
  created_at: number
  pid: string
  projectName: string
}

const recentSessions = ref<QuickAccessSession[]>([])
const loadingRecent = ref(false)

async function loadRecentSessions(): Promise<void> {
  if (projects.value.length === 0) {
    recentSessions.value = []
    return
  }
  loadingRecent.value = true
  try {
    const promises = projects.value.map(async (p) => {
      try {
        const list = await listSessions(p.pid)
        return list.map((s) => ({
          ...s,
          pid: p.pid,
          projectName: p.projectname,
        }))
      } catch (err) {
        console.error(`App.vue 加载科目 ${p.projectname} 的会话失败:`, err)
        return []
      }
    })
    const allLists = await Promise.all(promises)
    const combined = allLists.flat()
    combined.sort((a, b) => b.timestamp - a.timestamp)
    recentSessions.value = combined.slice(0, 6)
  } catch (err) {
    console.error('App.vue 加载最近会话失败:', err)
  } finally {
    loadingRecent.value = false
  }
}

watch(
  () => projects.value.map((p) => p.pid).join(','),
  () => {
    void loadRecentSessions()
  },
  { immediate: true }
)

watch(
  () => route.path,
  () => {
    void loadRecentSessions()
  }
)
</script>

<template>
  <main class="h-full bg-[#f3f4f6] text-[#1f2937]">
    <!-- 启动中 / 连接后端 -->
    <section v-if="bootstrapping" class="relative h-full w-full bg-[#f3f4f6]">
      <div class="absolute right-12 top-12 flex flex-col items-center gap-4 font-serif text-3xl font-extralight tracking-widest text-[#9ca3af] pointer-events-none select-none">
        <span>请</span>
        <span>稍</span>
        <span>后</span>
      </div>
    </section>

    <!-- 注册确认 / 密码设置（无需登录的特殊路径，直接挂载视图） -->
    <section v-else-if="!isAuthenticated && (route.name === 'set-password' || route.name === 'register-confirm')" class="flex h-full items-center justify-center px-4">
      <div class="w-full max-w-[1200px]">
        <RouterView />
      </div>
    </section>

    <!-- 登录 / 注册 / 找回密码 -->
    <section v-else-if="!isAuthenticated && route.name !== 'set-password' && route.name !== 'register-confirm'" class="flex h-full items-center justify-center px-4">
      <div class="w-full max-w-[420px] rounded-2xl border border-[#d1d5db]/80 bg-white p-6 shadow-md">
        <div class="mb-6">
          <svg viewBox="0 0 1323.48 135.75" class="mx-auto h-6 w-auto text-[#1f2937]" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <g>
              <polygon points="1279.68 40.08 1232.46 87.28 1185.25 135.43 1131.31 135.41 1193.93 72.76 1267.42 .83 1323.47 .8 1323.48 135.55 1279.92 135.6 1279.68 40.08"/>
              <polygon points="451.56 40.12 361.23 135.37 306.24 135.42 368.3 71.12 435.62 .77 493.41 .76 493.42 135.55 451.82 135.64 451.56 40.12"/>
              <polygon points="1198.02 .16 1253.17 .21 1189.78 62.64 1117.2 135.37 1063.28 135.44 1064.43 .32 1106.58 .3 1106.4 93.64 1152.58 46.43 1198.02 .16"/>
              <polygon points="144.55 103.03 144.63 135.56 0 135.64 .71 20.55 42.79 68.96 42.84 103.05 144.55 103.03"/>
              <path d="M602.51,135.75l-43.8-36.52-45.14-39.11,103.94-.32c4.94-.02,9.32-3.36,9.35-8.24l.08-12.64c.03-4.78-4.54-8.5-9.56-8.5l-107.01-.06-.18-30.21,116.27.06c10.86.83,20.76,3.33,28.65,10.64,12.28,11.38,12.87,30.1,10.82,46.89-2.23,18.3-16.25,31.63-34.75,32.24l-26.16.87,56.72,44.52-59.22.36Z"/>
              <polygon points="550.59 135.5 510.01 135.64 510.49 65.03 550.5 100.69 550.59 135.5"/>
              <path d="M1016.74,25.78c-10.65-14.34-24.58-22.32-41.5-25.28l52.48-.21c35.86,39.07,33.99,99.36-4.47,135.3l-116.46-.12c-38.04-37.14-36.92-98.41.79-135.47l51.15.47c-14.63,2.98-27.39,9.31-37.5,20.6-27.69,30.17-22.8,78.26,10.46,102.11,21.11,15.13,47.94,14.23,68.61-.92,30.72-22.51,38.79-64.94,16.43-96.47Z"/>
              <polygon points="997.74 41.57 965.63 96.25 935.09 41.57 997.74 41.57"/>
              <polygon points="42.47 59.86 .81 12.1 .82 .5 42.79 .44 42.47 59.86"/>
              <polygon points="299.77 51.2 299.73 79.66 244.55 79.61 217.62 79.65 202.43 62.36 162.35 15.44 162.5 .22 307.4 .22 307.35 30.37 204.22 30.4 204.26 51.25 299.77 51.2"/>
              <polygon points="299.57 104.31 299.87 127.44 291.12 135.6 161.38 135.6 162.56 24.5 204.09 72.56 204.15 104.36 299.57 104.31"/>
              <path d="M865.97.39l-2.47,135.17-52.36.07-93.02-97.69-29.59-31.6c-1.8-1.41-2.76-3.37-2.77-5.99l48.91-.14,87.54,96.53,2.18-96.3,41.58-.04Z"/>
              <polygon points="723.81 135.13 683.97 135.56 686 14.72 724.83 55.81 723.81 135.13"/>
            </g>
          </svg>
          <div class="mt-2 text-sm text-[#6b7280]">
            {{ authMode === 'forgot' ? '重置您的密码' : '登录后开始对话' }}
          </div>
        </div>

        <form class="space-y-4" @submit.prevent="handleSubmitAuth">
          <div v-if="authMode !== 'forgot'" class="grid grid-cols-2 rounded-xl border border-[#e5e7eb] bg-[#f9fafb] p-1">
            <button
              type="button"
              :class="[
                'h-9 rounded-lg px-3 text-sm font-medium transition-all duration-200 active:scale-95',
                authMode === 'login' ? 'bg-white text-[#111827] shadow-sm' : 'text-[#6b7280] hover:text-[#111827]',
              ]"
              @click="authMode = 'login'; clearAllNotifications()"
            >
              登录
            </button>
            <button
              type="button"
              :class="[
                'h-9 rounded-lg px-3 text-sm font-medium transition-all duration-200 active:scale-95',
                authMode === 'register' ? 'bg-white text-[#111827] shadow-sm' : 'text-[#6b7280] hover:text-[#111827]',
              ]"
              @click="authMode = 'register'; clearAllNotifications()"
            >
              注册
            </button>
          </div>

          <template v-if="authMode === 'login'">
            <label class="block">
              <span class="mb-1 block text-sm font-medium">邮箱</span>
              <input
                v-model="authForm.email"
                class="h-11 w-full rounded-lg border border-[#d1d5db] bg-white px-3 text-sm text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="email"
                type="email"
              />
            </label>

            <label class="block">
              <div class="mb-1 flex justify-between items-center">
                <span class="text-sm font-medium">密码</span>
                <button
                  type="button"
                  class="text-xs text-[#4b5563] hover:text-[#1f2937] hover:underline bg-transparent border-none p-0 cursor-pointer"
                  @click="authMode = 'forgot'; clearAllNotifications()"
                >
                  忘记密码？
                </button>
              </div>
              <input
                v-model="authForm.password"
                class="h-11 w-full rounded-lg border border-[#d1d5db] bg-white px-3 text-sm text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="current-password"
                type="password"
              />
            </label>
          </template>

          <template v-else-if="authMode === 'register'">
            <label class="block">
              <span class="mb-1 block text-sm font-medium">邮箱</span>
              <input
                v-model="authForm.email"
                class="h-11 w-full rounded-lg border border-[#d1d5db] bg-white px-3 text-sm text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="email"
                type="email"
                placeholder="请输入您的学校邮箱"
              />
            </label>
          </template>

          <template v-else-if="authMode === 'forgot'">
            <label class="block">
              <span class="mb-1 block text-sm font-medium">邮箱</span>
              <input
                v-model="authForm.email"
                class="h-11 w-full rounded-lg border border-[#d1d5db] bg-white px-3 text-sm text-[#1f2937] outline-none transition focus:border-[#1f2937] focus:ring-2 focus:ring-[#1f2937]/20"
                autocomplete="email"
                type="email"
                placeholder="请输入您注册的学校邮箱"
              />
            </label>
          </template>

          <button
            class="h-11 w-full rounded-xl border border-transparent bg-[#1f2937] px-4 text-sm font-semibold text-white transition-all duration-200 hover:bg-[#111827] active:scale-95 disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af] disabled:active:scale-100"
            :disabled="authSubmitting"
            type="submit"
          >
            {{ authSubmitting ? '处理中...' : authMode === 'login' ? '登录' : authMode === 'register' ? '发送激活邮件' : '发送重置密码邮件' }}
          </button>

          <div v-if="authMode === 'forgot'" class="text-center mt-2">
            <button
              type="button"
              class="text-sm text-[#6b7280] hover:text-[#1f2937] bg-transparent border-none cursor-pointer active:scale-95 transition-all duration-200"
              @click="authMode = 'login'; clearAllNotifications()"
            >
              &larr; 返回登录
            </button>
          </div>
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

      <aside
        :class="[
          'fixed z-50 flex h-full flex-col bg-white transition-all duration-300 md:relative',
          sidebarOpen
            ? 'w-56 translate-x-0'
            : '-translate-x-full overflow-hidden border-none md:w-0 md:translate-x-0',
        ]"
      >
        <div
          :class="[
            'flex h-full w-56 flex-shrink-0 flex-col px-2.5 py-4',
            'transition-opacity duration-150',
            sidebarOpen ? 'opacity-100 delay-100' : 'opacity-0',
          ]"
        >
          <div class="mb-5 mt-2 flex items-center justify-center gap-2 px-2">
            <button
              class="flex items-center gap-1 text-left"
              type="button"
              @click="closeSidebarOnMobile(); router.push({ name: 'overview' })"
            >
              <svg viewBox="0 0 1323.48 135.75" class="mx-auto h-8 w-auto max-w-[160px] text-[#1f2937] transition-colors duration-200" fill="currentColor" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <g>
                  <polygon points="1279.68 40.08 1232.46 87.28 1185.25 135.43 1131.31 135.41 1193.93 72.76 1267.42 .83 1323.47 .8 1323.48 135.55 1279.92 135.6 1279.68 40.08"/>
                  <polygon points="451.56 40.12 361.23 135.37 306.24 135.42 368.3 71.12 435.62 .77 493.41 .76 493.42 135.55 451.82 135.64 451.56 40.12"/>
                  <polygon points="1198.02 .16 1253.17 .21 1189.78 62.64 1117.2 135.37 1063.28 135.44 1064.43 .32 1106.58 .3 1106.4 93.64 1152.58 46.43 1198.02 .16"/>
                  <polygon points="144.55 103.03 144.63 135.56 0 135.64 .71 20.55 42.79 68.96 42.84 103.05 144.55 103.03"/>
                  <path d="M602.51,135.75l-43.8-36.52-45.14-39.11,103.94-.32c4.94-.02,9.32-3.36,9.35-8.24l.08-12.64c.03-4.78-4.54-8.5-9.56-8.5l-107.01-.06-.18-30.21,116.27.06c10.86.83,20.76,3.33,28.65,10.64,12.28,11.38,12.87,30.1,10.82,46.89-2.23,18.3-16.25,31.63-34.75,32.24l-26.16.87,56.72,44.52-59.22.36Z"/>
                  <polygon points="550.59 135.5 510.01 135.64 510.49 65.03 550.5 100.69 550.59 135.5"/>
                  <path d="M1016.74,25.78c-10.65-14.34-24.58-22.32-41.5-25.28l52.48-.21c35.86,39.07,33.99,99.36-4.47,135.3l-116.46-.12c-38.04-37.14-36.92-98.41.79-135.47l51.15.47c-14.63,2.98-27.39,9.31-37.5,20.6-27.69,30.17-22.8,78.26,10.46,102.11,21.11,15.13,47.94,14.23,68.61-.92,30.72-22.51,38.79-64.94,16.43-96.47Z"/>
                  <polygon points="997.74 41.57 965.63 96.25 935.09 41.57 997.74 41.57"/>
                  <polygon points="42.47 59.86 .81 12.1 .82 .5 42.79 .44 42.47 59.86"/>
                  <polygon points="299.77 51.2 299.73 79.66 244.55 79.61 217.62 79.65 202.43 62.36 162.35 15.44 162.5 .22 307.4 .22 307.35 30.37 204.22 30.4 204.26 51.25 299.77 51.2"/>
                  <polygon points="299.57 104.31 299.87 127.44 291.12 135.6 161.38 135.6 162.56 24.5 204.09 72.56 204.15 104.36 299.57 104.31"/>
                  <path d="M865.97.39l-2.47,135.17-52.36.07-93.02-97.69-29.59-31.6c-1.8-1.41-2.76-3.37-2.77-5.99l48.91-.14,87.54,96.53,2.18-96.3,41.58-.04Z"/>
                  <polygon points="723.81 135.13 683.97 135.56 686 14.72 724.83 55.81 723.81 135.13"/>
                </g>
              </svg>
            </button>
          </div>

          <button
            class="mx-1 mb-1.5 flex h-8 items-center justify-start gap-1.5 rounded-xl pl-4 pr-2 text-left transition-all duration-200 active:scale-95"
            :class="[
              $route.name === 'library'
                ? 'bg-[#1f2937] text-white font-medium shadow-sm'
                : 'bg-[#f3f4f6]/80 text-[#4b5563] hover:bg-[#e5e7eb] hover:text-[#1f2937]'
            ]"
            type="button"
            title="我的仓库"
            @click="closeSidebarOnMobile(); router.push({ name: 'library' })"
          >
            <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-6 4h4" />
            </svg>
            <span class="text-xs whitespace-nowrap font-hans">我的仓库</span>
          </button>

          <button
            class="mx-1 mb-3 flex h-8 items-center justify-start gap-1.5 rounded-xl pl-4 pr-2 text-left transition-all duration-200 active:scale-95"
            :class="[
              $route.name === 'community'
                ? 'bg-[#1f2937] text-white font-medium shadow-sm'
                : 'bg-[#f3f4f6]/80 text-[#4b5563] hover:bg-[#e5e7eb] hover:text-[#1f2937]'
            ]"
            type="button"
            title="技能社区"
            @click="closeSidebarOnMobile(); router.push({ name: 'community' })"
          >
            <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            <span class="text-xs whitespace-nowrap font-hans">技能社区</span>
          </button>

          <div class="no-scrollbar flex-1 overflow-y-auto">
            <div class="mb-2 pl-4 text-xs font-medium text-[#6b7280] font-serif-hans">我的科目</div>
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
                    'flex h-8 w-auto mx-1 cursor-pointer items-center justify-start gap-2 rounded-xl pl-4 pr-2 text-left text-[13px] transition-colors',
                    ($route.params.pid as string | undefined) === project.pid
                      ? 'bg-[#e5e7eb] font-medium'
                      : 'hover:bg-[#e5e7eb]',
                  ]"
                  @click="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: project.pid } })"
                  @keydown.enter.prevent="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: project.pid } })"
                >
                  <span class="font-hans flex-1 truncate text-[13px]">{{ project.projectname }}</span>
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
                class="flex w-full items-center justify-start px-4 py-1 bg-transparent border-none outline-none text-[#9ca3af] hover:text-[#4b5563] transition-colors select-none cursor-pointer"
                @click="closeSidebarOnMobile(); router.push({ name: 'overview' })"
              >
                <span class="text-xs whitespace-nowrap">查看全部科目</span>
              </button>

              <!-- 最近会话列表 -->
              <template v-if="recentSessions.length > 0">
                <div class="mx-4 my-2 border-t border-[#e5e7eb]/60" />
                <div class="mb-2 pl-4 text-xs font-medium text-[#6b7280] font-serif-hans">最近会话</div>
                <div class="flex flex-col gap-1">
                  <div
                    v-for="session in recentSessions"
                    :key="session.sid"
                    role="button"
                    tabindex="0"
                    :class="[
                      'flex h-8 w-auto mx-1 cursor-pointer items-center justify-start gap-2 rounded-xl pl-4 pr-2 text-left text-[13px] transition-colors',
                      ($route.params.sid as string | undefined) === session.sid
                        ? 'bg-[#e5e7eb] font-medium'
                        : 'hover:bg-[#e5e7eb]',
                    ]"
                    @click="closeSidebarOnMobile(); router.push({ name: 'chat', params: { pid: session.pid, sid: session.sid } })"
                    @keydown.enter.prevent="closeSidebarOnMobile(); router.push({ name: 'chat', params: { pid: session.pid, sid: session.sid } })"
                  >
                    <span class="font-hans flex-1 truncate text-[13px]">{{ session.projectName }} / {{ session.sessionname }}</span>
                  </div>
                </div>
              </template>
            </div>
          </div>

          <div class="mt-3 flex-shrink-0 flex flex-col space-y-0.5 pt-3 border-t border-[#e5e7eb]/60">
            <button
              class="flex h-8 w-auto mx-1 cursor-not-allowed items-center justify-start gap-1.5 rounded-xl border border-transparent pl-4 pr-2 text-left text-[#9ca3af]"
              type="button"
              disabled
              title="暂未实现"
            >
              <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span class="text-xs whitespace-nowrap">文档</span>
            </button>
            <button
              class="flex h-8 w-auto mx-1 cursor-not-allowed items-center justify-start gap-1.5 rounded-xl border border-transparent pl-4 pr-2 text-left text-[#9ca3af]"
              type="button"
              disabled
              title="暂未实现"
            >
              <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <span class="text-xs whitespace-nowrap">仪表盘</span>
            </button>
            <button
              class="flex h-8 w-auto mx-1 items-center justify-start gap-1.5 rounded-xl border border-transparent pl-4 pr-2 text-left text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95"
              type="button"
              title="AI 模型配置"
              @click="showSettingsDialog = true"
            >
              <svg class="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span class="text-xs whitespace-nowrap">设置</span>
            </button>
            <div
              class="mt-1.5 mx-1 flex cursor-pointer items-center gap-2 rounded-xl px-2 py-2 shadow-sm transition-all duration-200 hover:bg-[#e5e7eb] active:scale-[0.98]"
              title="个人中心"
              @click="showUserProfileDialog = true"
            >
              <div class="relative flex h-7.5 w-7.5 flex-shrink-0 items-center justify-center rounded-full bg-[#e5e7eb] text-sm overflow-hidden border border-slate-200 select-none">
                <!-- 底层灰底首字母占位 -->
                <span class="font-semibold text-slate-500 text-xs">{{ avatarLetter }}</span>
                <!-- 顶层图片覆盖 -->
                <img 
                  v-if="currentUser?.head_file && !hasAvatarError" 
                  :src="`${API_BASE_URL}/auth/avatar/${currentUser.uuid}?t=${avatarVersion}`" 
                  class="absolute inset-0 h-full w-full object-cover" 
                  alt="Avatar" 
                  @error="handleAvatarError"
                />
              </div>
              <div class="min-w-0 flex-1">
                <div class="truncate text-[12px] font-semibold text-[#1f2937] leading-none">{{ displayUser }}</div>
                <div class="whitespace-nowrap text-[9.5px] sm:text-[10px] text-[#6b7280] mt-1 leading-none" :title="currentUser?.email">
                  {{ currentUser?.email || '个人中心' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 主内容区 -->
      <section class="relative flex min-w-0 flex-1 flex-col bg-[#f3f4f6] transition-all duration-300">
        <header class="absolute top-0 left-0 right-0 z-30 flex h-14 flex-shrink-0 items-center justify-between px-4 pointer-events-none">
          <div
            class="flex min-w-0 items-center gap-3 overflow-hidden pointer-events-auto px-3 py-1 rounded-full transition-all duration-300 scale-90 origin-left"
            :class="[
              editingSkill
                ? 'bg-transparent border border-transparent'
                : hasScrolled || isMobile
                  ? 'bg-white/80 backdrop-blur-md border border-[#e5e7eb] shadow-sm'
                  : 'bg-transparent border border-transparent'
            ]"
          >
            <button
              class="flex-shrink-0 rounded-full p-2 text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95"
              type="button"
              title="切换侧边栏"
              @click="sidebarOpen = !sidebarOpen"
            >
              <svg class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div class="flex items-center gap-2 truncate text-sm font-medium text-[#4b5563] pr-2">
              <template v-if="$route.name === 'overview'">
                <span class="text-[#1f2937] font-semibold">科目总览</span>
                <span v-if="preparing" class="text-xs text-[#9ca3af]">准备中</span>
              </template>
              <template v-else-if="$route.name === 'community'">
                <span class="text-[#1f2937] font-semibold text-sm">技能社区</span>
              </template>
              <template v-else-if="$route.name === 'library'">
                <span class="text-[#1f2937] font-semibold text-sm">我的仓库</span>
              </template>
              <template v-else-if="$route.name === 'subject' && subjectProject">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937] transition-colors" @click="router.push({ name: 'overview' })">科目</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937] font-semibold">{{ truncateText(subjectProject.projectname, 20) }}</span>
              </template>
              <template v-else-if="$route.name === 'chat' && chatProject && chatSession">
                <span class="hidden md:inline cursor-pointer text-[#9ca3af] hover:text-[#1f2937] transition-colors" @click="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: $route.params.pid } })">{{ truncateText(chatProject.projectname, 8) }}</span>
                <span class="hidden md:inline text-[#9ca3af]">/</span>
                <span class="text-[#1f2937] font-semibold">{{ truncateText(chatSession.sessionname, 25) }}</span>
              </template>
            </div>
          </div>
        </header>
        <!-- 全局错误提示已移至顶栏下方悬浮显示 -->

        <div class="relative flex-1 overflow-hidden">
          <RouterView v-slot="{ Component, route: rv }">
            <!-- 侧向淡出过渡：forward=右进左出，backward=左进右出。
                 用单根 <div> 包裹路由组件再套 <Transition>：<Transition> 只能对单根子节点
                 应用过渡，而部分视图（如 SubjectView）是多根（主体 + 弹窗），直接包裹会失效。
                 包裹层 absolute inset-0 充满容器，内部视图的 absolute inset-0 仍正确解析。 -->
            <Transition :name="`view-slide-${navDirection}`" mode="out-in">
              <div
                v-if="Component"
                :key="rv.name === 'chat' ? `${rv.params.pid}:${rv.params.sid}` : String(rv.name ?? '')"
                class="absolute inset-0 transition-[bottom] duration-100 ease-out"
                :style="{ bottom: 'var(--keyboard-offset, 0px)' }"
              >
                <component :is="Component" />
              </div>
            </Transition>
          </RouterView>

        </div>
      </section>

      <!-- 会话技能侧边栏（仅 chat/subject 路由生效） -->
      <ChatSkillSidebar v-if="$route.name === 'chat' || $route.name === 'subject'" />

      <!-- 右上角固定按钮组（z-index 高于侧边栏） -->
      <div v-if="$route.name === 'chat' || $route.name === 'subject'" class="fixed top-3 right-4 z-50 flex items-center gap-1.5">
        <!-- 关闭技能编辑按钮（仅聊天页编辑时显示） -->
        <button
          v-if="editingSkill && $route.name === 'chat'"
          class="flex h-8 w-8 items-center justify-center rounded-full border border-[#d1d5db] bg-white text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95"
          type="button"
          title="关闭编辑"
          @click="closeEditor"
        >
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <!-- 新建对话按钮（仅聊天页显示） -->
        <button
          v-if="$route.name === 'chat'"
          class="flex h-8 w-8 items-center justify-center rounded-full border border-[#d1d5db] bg-white text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95"
          type="button"
          title="新建对话"
          @click="router.push({ name: 'subject', params: { pid: $route.params.pid } })"
        >
          <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
        </button>

        <!-- 技能侧边栏切换按钮 -->
        <button
          class="flex h-8 w-8 items-center justify-center rounded-full border border-[#d1d5db] bg-white text-[#4b5563] transition-all duration-200 hover:bg-[#e5e7eb] active:scale-95"
          type="button"
          :title="chatSidebarOpen ? '收起技能面板' : '展开技能面板'"
          @click="toggleChatSidebar"
        >
          <svg
            class="h-4 w-4 transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)]"
            :class="chatSidebarOpen ? 'rotate-180' : 'rotate-0'"
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
    </section>

    <Transition name="dialog-fade" appear>
      <SkillManagerDialog
        v-if="showUserSkillManager && userSkillSpace"
        :space="userSkillSpace"
        title="我的技能（用户级）"
        @close="closeUserSkillManager"
      />
    </Transition>
    <Transition name="dialog-fade" appear>
      <SkillManagerDialog
        v-if="showProjectSkillManager && projectSkillSpace"
        :space="projectSkillSpace"
        title="项目技能"
        @close="closeProjectSkillManager"
      />
    </Transition>
    <Transition name="dialog-fade" appear>
      <SettingsDialog
        v-if="showSettingsDialog"
        @close="showSettingsDialog = false"
      />
    </Transition>
    <Transition name="dialog-fade" appear>
      <ConfirmDialog
        v-if="confirmState.open"
        :title="confirmState.title"
        :message="confirmState.message"
        :confirm-text="confirmState.confirmText"
        :cancel-text="confirmState.cancelText"
        :tone="confirmState.tone"
        @confirm="resolveConfirm"
        @cancel="cancelConfirm"
      />
    </Transition>

    <!-- 个人主页管理弹窗 -->
    <UserProfileDialog
      :show="showUserProfileDialog"
      @close="showUserProfileDialog = false"
      @logout="handleLogout"
    />

    <!-- 全局悬浮提示框堆叠容器 (黑底白字，从屏幕正上方/顶栏下方弹出) -->
    <div class="fixed top-14 left-1/2 -translate-x-1/2 z-[9999] w-[calc(100%-2rem)] sm:w-[520px] pointer-events-none flex flex-col gap-2 px-1">
      <TransitionGroup name="toast-slide">
        <div
          v-for="item in notifications"
          :key="item.id"
          class="w-full bg-neutral-950/95 backdrop-blur-md text-white rounded-2xl shadow-[0_20px_40px_-10px_rgba(0,0,0,0.45)] border border-neutral-800/80 overflow-hidden pointer-events-auto toast-slide-item"
          role="alert"
        >
          <div class="flex items-center justify-between p-4 gap-3.5">
            <!-- 勾/叉 图标 -->
            <div v-if="item.type === 'success'" class="flex items-center justify-center w-8 h-8 rounded-full bg-emerald-500/10 text-emerald-400 flex-shrink-0">
              <svg class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div v-else class="flex items-center justify-center w-8 h-8 rounded-full bg-rose-500/10 text-rose-400 flex-shrink-0">
              <svg class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>

            <!-- 内容 -->
            <div class="flex-1 min-w-0 text-sm font-medium tracking-wide leading-relaxed text-neutral-100">
              {{ item.message }}
            </div>

            <!-- 右侧操作 -->
            <div class="flex items-center gap-1 flex-shrink-0">
              <!-- 展开详情按钮 -->
              <button
                v-if="item.details"
                type="button"
                class="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800/80 transition-all duration-200 active:scale-95 focus:outline-none cursor-pointer"
                :title="item.expanded ? '收起详情' : '展开详情'"
                @click="toggleNotificationExpanded(item.id)"
              >
                <svg
                  class="h-4 w-4 transform transition-transform duration-300"
                  :class="{ 'rotate-180': item.expanded }"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <!-- 关闭按钮 -->
              <button
                type="button"
                class="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800/80 transition-all duration-200 active:scale-95 focus:outline-none cursor-pointer"
                title="关闭"
                @click="removeNotification(item.id)"
              >
                <svg class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 详情面板 -->
          <div
            v-if="item.details && item.expanded"
            class="border-t border-neutral-800/80 px-4.5 py-3.5 bg-black/40 max-h-48 overflow-y-auto"
          >
            <div class="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold mb-1.5">错误详情</div>
            <pre class="text-xs text-neutral-300 font-mono break-all whitespace-pre-wrap leading-relaxed select-text">{{ item.details }}</pre>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </main>
</template>

<style>
/*
 * 路由视图侧向淡出过渡
 * 使用 cubic-bezier(0.2, 0.8, 0.2, 1) 与项目其他动画保持一致
 * 向前（overview→subject→chat）：新视图从右进入，旧视图向左退出
 * 向后（chat→subject→overview）：新视图从左进入，旧视图向右退出
 */

/* ── 向前导航（进入右侧，退出左侧） ── */
.view-slide-forward-enter-active,
.view-slide-forward-leave-active {
  transition:
    opacity 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
.view-slide-forward-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.view-slide-forward-enter-to {
  opacity: 1;
  transform: translateX(0);
}
.view-slide-forward-leave-from {
  opacity: 1;
  transform: translateX(0);
}
.view-slide-forward-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}

/* ── 向后导航（进入左侧，退出右侧） ── */
.view-slide-backward-enter-active,
.view-slide-backward-leave-active {
  transition:
    opacity 160ms cubic-bezier(0.2, 0.8, 0.2, 1),
    transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
.view-slide-backward-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}
.view-slide-backward-enter-to {
  opacity: 1;
  transform: translateX(0);
}
.view-slide-backward-leave-from {
  opacity: 1;
  transform: translateX(0);
}
.view-slide-backward-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* ── 全局悬浮提示框弹出过渡 ── */
.toast-slide-item {
  transform: translateY(0);
}
.toast-slide-enter-active {
  transition: transform 380ms cubic-bezier(0.2, 0.8, 0.2, 1), opacity 250ms ease;
}
.toast-slide-leave-active {
  position: absolute;
  width: 100%;
  transition: transform 250ms cubic-bezier(0.2, 0.8, 0.2, 1), opacity 150ms ease;
}
.toast-slide-move {
  transition: transform 300ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
.toast-slide-enter-from,
.toast-slide-leave-to {
  transform: translateY(-20px) scale(0.95);
  opacity: 0;
}
.toast-slide-enter-to,
.toast-slide-leave-from {
  transform: translateY(0) scale(1);
  opacity: 1;
}
</style>
