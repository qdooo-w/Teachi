<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SkillManagerDialog from './components/SkillManagerDialog.vue'
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
import { PREVIEW_PROJECT_LIMIT, API_BASE_URL } from './config'

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

// ── 路由层级深度：overview/community=0，subject=1，chat=2 ──────────────────
const ROUTE_DEPTH: Record<string, number> = {
  overview: 0,
  community: 0,
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

const confirmDelete = ref<{ id: string; name: string } | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

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

function askDeleteProject(project: ProjectItem): void {
  openMenuKey.value = null
  deleteError.value = ''
  confirmDelete.value = { id: project.pid, name: project.projectname }
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
    await deleteProject(target.id)
    // 如果正在查看被删除的项目或其会话，回到总览
    if (route.params.pid === target.id) {
      await router.replace({ name: 'overview' })
    }
    removeProject(target.id)
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
  return {
    title: '删除科目',
    message: `确定删除「${target.name}」？该科目下的所有会话和消息也会被一并删除，操作不可恢复。`,
  }
})

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
async function handleLogout(): Promise<void> {
  await authLogout()
  resetProjects()
  errorMessage.value = ''
  showUserSkillManager.value = false
  showProjectSkillManager.value = false
  showSettingsDialog.value = false
  openMenuKey.value = null
  renamingKey.value = null
  confirmDelete.value = null
  deleteError.value = ''
  await router.replace({ name: 'overview' })
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
function updateKeyboardOffset() {
  if (window.visualViewport) {
    const offset = window.innerHeight - window.visualViewport.height
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
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', updateKeyboardOffset)
    window.visualViewport.removeEventListener('scroll', updateKeyboardOffset)
  }
})
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
          <div class="text-2xl font-bold tracking-normal">Learnova</div>
          <div class="mt-1 text-sm text-[#6b7280]">
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
              @click="authMode = 'login'; authError = ''"
            >
              登录
            </button>
            <button
              type="button"
              :class="[
                'h-9 rounded-lg px-3 text-sm font-medium transition-all duration-200 active:scale-95',
                authMode === 'register' ? 'bg-white text-[#111827] shadow-sm' : 'text-[#6b7280] hover:text-[#111827]',
              ]"
              @click="authMode = 'register'; authError = ''"
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
                  @click="authMode = 'forgot'; authError = ''"
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

          <p v-if="authError" class="rounded-xl border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
            {{ authError }}
          </p>

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
              @click="authMode = 'login'; authError = ''"
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
        <div class="flex h-full w-56 flex-shrink-0 flex-col px-2.5 py-4">
          <div class="mb-5 mt-2 flex items-center justify-start gap-2 pl-4 pr-2">
            <button
              class="flex items-center gap-1 text-left"
              type="button"
              @click="closeSidebarOnMobile(); router.push({ name: 'overview' })"
            >
              <span 
                class="text-[23px] font-bold tracking-tight"
                style="font-family: 'Source Han Serif SC', 'Source Han Serif CN', 'Noto Serif CJK SC', 'Songti SC', 'SimSun', serif;"
              >
                Learnova
              </span>
            </button>
          </div>

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
            <span class="text-xs whitespace-nowrap">技能社区</span>
          </button>

          <div class="no-scrollbar flex-1 overflow-y-auto">
            <div class="mb-2 pl-4 text-xs font-medium text-[#6b7280]">我的科目</div>
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
        <header class="flex h-14 flex-shrink-0 items-center justify-between px-4">
          <div class="flex min-w-0 items-center gap-3 overflow-hidden">
            <button
              class="flex-shrink-0 rounded p-2 text-[#4b5563] transition-colors hover:bg-[#e5e7eb]"
              type="button"
              title="切换侧边栏"
              @click="sidebarOpen = !sidebarOpen"
            >
              <svg class="h-5 w-5" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div class="flex items-center gap-2 truncate text-sm font-medium text-[#4b5563]">
              <template v-if="$route.name === 'overview'">
                <span class="text-[#1f2937]">科目总览</span>
                <span v-if="preparing" class="text-xs text-[#9ca3af]">准备中</span>
              </template>
              <template v-else-if="$route.name === 'community'">
                <span class="text-[#1f2937] font-semibold text-sm">技能社区</span>
              </template>
              <template v-else-if="$route.name === 'subject' && subjectProject">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="router.push({ name: 'overview' })">科目</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(subjectProject.projectname, 20) }}</span>
              </template>
              <template v-else-if="$route.name === 'chat' && chatProject && chatSession">
                <span class="hidden md:inline cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: $route.params.pid } })">{{ truncateText(chatProject.projectname, 8) }}</span>
                <span class="hidden md:inline text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(chatSession.sessionname, 25) }}</span>
              </template>
            </div>
          </div>

          <div class="flex items-center gap-1">
            <button
              v-if="$route.name === 'chat'"
              class="flex h-9 items-center gap-1 rounded border border-transparent px-3 text-sm text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="新建对话"
              @click="router.push({ name: 'subject', params: { pid: $route.params.pid } })"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              <span class="hidden md:inline">新建对话</span>
            </button>
            <span class="hidden md:flex h-9 items-center gap-1 px-2 text-sm text-[#9ca3af]">
              Skills管理
              <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </span>
            <button
              class="flex h-9 w-9 items-center justify-center rounded border border-transparent text-[#9ca3af] cursor-not-allowed"
              type="button"
              title="技能仓库（暂不可用）"
              disabled
            >
              <svg class="h-4.5 w-4.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
            <button
              class="flex h-9 w-9 items-center justify-center rounded border border-transparent text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="我的技能"
              @click="showUserSkillManager = true"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM12 14a7 7 0 0 0-7 7h14a7 7 0 0 0-7-7z" />
              </svg>
            </button>
            <button
              v-if="projectSkillSpace"
              class="flex h-9 w-9 items-center justify-center rounded border border-transparent text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
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

        <!-- 全局错误提示（sidebar 改名 / 删除 / token 恢复失败等会写入 errorMessage） -->
        <div
          v-if="errorMessage"
          class="mx-4 mt-2 flex items-center justify-between rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]"
          role="alert"
        >
          <span class="truncate">{{ errorMessage }}</span>
          <button
            class="ml-3 flex-shrink-0 text-[#9a3412] hover:text-[#7c2d12]"
            type="button"
            title="关闭"
            @click="errorMessage = ''"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

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
    </Transition>

    <!-- 个人主页管理弹窗 -->
    <UserProfileDialog
      :show="showUserProfileDialog"
      @close="showUserProfileDialog = false"
      @logout="handleLogout"
    />
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
</style>
