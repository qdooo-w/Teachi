<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SkillManagerDialog from './components/SkillManagerDialog.vue'
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
  type ProjectItem,
  type SessionItem,
} from './api'
import { type FileSpace } from './skills'
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

// ── 路由 / 共享状态 ─────────────────────────────────────────────────────────
const router = useRouter()
const route = useRoute()

const { projects, loadProjects, resetProjects, upsertProject, removeProject } = useProjects()
const { sidebarOpen, isMobile, handleResize, closeSidebarOnMobile } = useLayout()

const previewProjects = computed(() => projects.value.slice(0, 10))

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

const projectSkillSpace = computed<FileSpace | null>(() => {
  const pid = route.params.pid as string | undefined
  return pid ? { kind: 'project', pid } : null
})
const userSkillSpace = computed<FileSpace | null>(() => {
  const userId = getCurrentUserId()
  return token.value && userId ? { kind: 'user', userId } : null
})

function closeProjectSkillManager(): void {
  showProjectSkillManager.value = false
  // 通知聊天视图刷新项目技能列表（技能可能在对话框中被新增/修改/删除）
  window.dispatchEvent(new CustomEvent('teachi-project-skills-changed'))
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
  openMenuKey.value = null
  renamingKey.value = null
  confirmDelete.value = null
  deleteError.value = ''
  await router.replace({ name: 'overview' })
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
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
                    ($route.params.pid as string | undefined) === project.pid
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
              <template v-if="$route.name === 'overview'">
                <span class="text-[#1f2937]">科目总览</span>
                <span v-if="preparing" class="text-xs text-[#9ca3af]">准备中</span>
              </template>
              <template v-else-if="$route.name === 'subject' && subjectProject">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="router.push({ name: 'overview' })">科目</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(subjectProject.projectname, 20) }}</span>
              </template>
              <template v-else-if="$route.name === 'chat' && chatProject && chatSession">
                <span class="cursor-pointer text-[#9ca3af] hover:text-[#1f2937]" @click="closeSidebarOnMobile(); router.push({ name: 'subject', params: { pid: $route.params.pid } })">{{ truncateText(chatProject.projectname, 8) }}</span>
                <span class="text-[#9ca3af]">/</span>
                <span class="text-[#1f2937]">{{ truncateText(chatSession.sessionname, 15) }}</span>
              </template>
            </div>
          </div>

          <div class="flex items-center gap-1">
            <button
              v-if="$route.name === 'chat'"
              class="flex h-9 items-center gap-1 rounded-xl border border-transparent px-3 text-sm text-[#4b5563] transition-colors hover:border-[#d1d5db] hover:bg-[#e5e7eb]"
              type="button"
              title="新建对话"
              @click="router.push({ name: 'subject', params: { pid: $route.params.pid } })"
            >
              <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              <span class="hidden sm:inline">新建对话</span>
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
              v-if="projectSkillSpace"
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
          <RouterView v-slot="{ Component, route: rv }">
            <component
              :is="Component"
              v-if="Component"
              :key="rv.name === 'chat' ? `${rv.params.pid}:${rv.params.sid}` : String(rv.name ?? '')"
            />
          </RouterView>

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
      @close="closeProjectSkillManager"
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
