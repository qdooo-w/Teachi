<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RowMenu from '../components/RowMenu.vue'
import RenameInline from '../components/RenameInline.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import {
  createSession,
  deleteSession,
  getErrorMessage,
  listSessions,
  renameSession,
  type ProjectItem,
  type SessionItem,
} from '../api'
import { useProjects } from '../composables/useProjects'
import { useLayout } from '../composables/useLayout'
import { readSkill, PROJECT_DESC_SKILL, parseSkillFile } from '../skills'

const route = useRoute()
const router = useRouter()
const { projects, loadProjects } = useProjects()
const { closeSidebarOnMobile } = useLayout()

const pid = computed(() => route.params.pid as string)
const currentProject = computed<ProjectItem | null>(() =>
  projects.value.find((p) => p.pid === pid.value) ?? null,
)

const sessions = ref<SessionItem[]>([])
const newSessionDraft = ref('')
const newSessionName = ref('')
const showCreatePanel = ref(false)
const sessionNameInput = ref<HTMLInputElement | null>(null)
const messageInput = ref<HTMLTextAreaElement | null>(null)
const creatingSession = ref(false)
const errorMessage = ref('')

async function openCreatePanel(): Promise<void> {
  showCreatePanel.value = true
  await nextTick()
  sessionNameInput.value?.focus()
}

function closeCreatePanel(): void {
  if (creatingSession.value) return
  showCreatePanel.value = false
  newSessionName.value = ''
  newSessionDraft.value = ''
  errorMessage.value = ''
}

// ── 项目简介 ──────────────────────────────────────────────────────────────────
const DESC_COLLAPSE_LIMIT = 150
const projectDesc = ref('')
const descExpanded = ref(false)

const descTruncated = computed(() =>
  projectDesc.value.length > DESC_COLLAPSE_LIMIT && !descExpanded.value
    ? projectDesc.value.slice(0, DESC_COLLAPSE_LIMIT).trimEnd() + '…'
    : projectDesc.value,
)
const needsCollapse = computed(() => projectDesc.value.length > DESC_COLLAPSE_LIMIT)

async function loadProjectDesc(currentPid: string): Promise<void> {
  projectDesc.value = ''
  descExpanded.value = false
  try {
    const space = { kind: 'project' as const, pid: currentPid }
    const { content } = await readSkill(space, PROJECT_DESC_SKILL)
    const parsed = parseSkillFile(content)
    if (parsed.ok && parsed.fields) {
      projectDesc.value = parsed.fields.body.trim()
    }
  } catch {
    // 简介不存在时静默忽略
  }
}

const openMenuKey = ref<string | null>(null)
const renamingKey = ref<string | null>(null)
const renameSubmitting = ref(false)
const confirmDelete = ref<{ id: string; name: string } | null>(null)
const deleteSubmitting = ref(false)
const deleteError = ref('')

function sessionKey(sid: string): string {
  return `session:${sid}`
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

async function loadSessionsFor(nextPid: string): Promise<void> {
  try {
    sessions.value = await listSessions(nextPid)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  }
}

async function goToSession(session: SessionItem): Promise<void> {
  closeSidebarOnMobile()
  await router.push({ name: 'chat', params: { pid: pid.value, sid: session.sid } })
}

async function handleStartNewSessionFromSubject(): Promise<void> {
  const name = newSessionName.value.trim()
  const text = newSessionDraft.value.trim()
  if (!name || !text || creatingSession.value) return

  creatingSession.value = true
  errorMessage.value = ''
  try {
    const session = await createSession(pid.value, name)
    sessions.value = [session, ...sessions.value]
    closeCreatePanel()
    await router.push({
      name: 'chat',
      params: { pid: pid.value, sid: session.sid },
      query: { initial: text },
    })
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    creatingSession.value = false
  }
}

function toggleMenu(key: string): void {
  openMenuKey.value = openMenuKey.value === key ? null : key
}
function closeMenu(): void { openMenuKey.value = null }
function startRename(key: string): void { renamingKey.value = key; openMenuKey.value = null }
function cancelRename(): void { renamingKey.value = null }

async function submitSessionRename(session: SessionItem, nextName: string): Promise<void> {
  renameSubmitting.value = true
  errorMessage.value = ''
  try {
    const updated = await renameSession(session.sid, nextName)
    sessions.value = sessions.value.map((item) => (item.sid === updated.sid ? updated : item))
    renamingKey.value = null
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    renameSubmitting.value = false
  }
}

function askDeleteSession(session: SessionItem): void {
  openMenuKey.value = null
  deleteError.value = ''
  confirmDelete.value = { id: session.sid, name: session.sessionname }
}

function cancelDelete(): void {
  if (deleteSubmitting.value) return
  confirmDelete.value = null
  deleteError.value = ''
}

async function performDelete(): Promise<void> {
  if (!confirmDelete.value || deleteSubmitting.value) return
  const target = confirmDelete.value
  deleteSubmitting.value = true
  deleteError.value = ''
  try {
    await deleteSession(target.id)
    sessions.value = sessions.value.filter((s) => s.sid !== target.id)
    confirmDelete.value = null
  } catch (error) {
    deleteError.value = getErrorMessage(error)
  } finally {
    deleteSubmitting.value = false
  }
}

onMounted(async () => {
  if (projects.value.length === 0) await loadProjects()
  if (!currentProject.value) {
    await router.replace({ name: 'overview' })
    return
  }
  await Promise.all([loadSessionsFor(pid.value), loadProjectDesc(pid.value)])
})

watch(
  () => pid.value,
  async (nextPid, prevPid) => {
    if (!nextPid || nextPid === prevPid) return
    sessions.value = []
    if (!currentProject.value) {
      await router.replace({ name: 'overview' })
      return
    }
    await Promise.all([loadSessionsFor(nextPid), loadProjectDesc(nextPid)])
  },
)

watch(
  () => currentProject.value?.projectname,
  (name) => {
    if (name) document.title = `${name} · Teachi`
  },
  { immediate: true },
)
</script>

<template>
  <div class="absolute inset-0 flex flex-col overflow-y-auto px-4 pt-5 md:px-6">
    <div v-if="currentProject" class="mx-auto flex w-full max-w-3xl flex-1 flex-col">
      <div class="mb-8">
        <h2 class="mb-2 text-3xl font-bold">{{ currentProject.projectname }}</h2>
        <p class="text-sm text-[#6b7280]">创建于 {{ formatDate(currentProject.created_at) }}</p>
      </div>

      <!-- 项目简介块：blockquote 风格 -->
      <div v-if="projectDesc" class="mb-5 flex items-start gap-3">
        <div class="mt-0.5 w-0.5 flex-shrink-0 self-stretch rounded-full bg-[#d1d5db]"></div>
        <div class="min-w-0 flex-1">
          <p class="whitespace-pre-wrap text-sm leading-snug text-[#4b5563]">{{ descTruncated }}</p>
          <button
            v-if="needsCollapse"
            type="button"
            class="mt-1 text-xs text-[#9ca3af] hover:text-[#6b7280]"
            @click="descExpanded = !descExpanded"
          >
            {{ descExpanded ? '收起' : '展开' }}
          </button>
        </div>
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

      <div class="mt-auto w-full pb-4">
        <p v-if="errorMessage" class="mb-2 rounded-md border border-[#efb3a7] bg-[#fff7ed] px-3 py-2 text-sm text-[#9a3412]">
          {{ errorMessage }}
        </p>

        <!-- 创建面板 -->
        <div v-if="showCreatePanel" class="rounded-3xl bg-white p-4 shadow-sm">
          <input
            ref="sessionNameInput"
            v-model="newSessionName"
            type="text"
            class="mb-3 w-full border-none bg-transparent text-base font-medium text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
            placeholder="会话名称"
            :disabled="creatingSession"
            @keydown.enter.prevent="messageInput?.focus()"
            @keydown.esc.prevent="closeCreatePanel"
          />
          <div class="mb-3 border-t border-[#f3f4f6]" />
          <textarea
            ref="messageInput"
            v-model="newSessionDraft"
            class="max-h-32 w-full resize-none border-none bg-transparent text-sm leading-normal text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
            placeholder="输入第一条消息..."
            rows="2"
            :disabled="creatingSession"
            @keydown.ctrl.enter.prevent="handleStartNewSessionFromSubject"
            @keydown.meta.enter.prevent="handleStartNewSessionFromSubject"
            @keydown.esc.prevent="closeCreatePanel"
          />
          <div class="mt-3 flex items-center justify-end gap-2">
            <button
              type="button"
              class="rounded-2xl px-4 py-2 text-sm text-[#6b7280] transition hover:bg-[#f3f4f6]"
              :disabled="creatingSession"
              @click="closeCreatePanel"
            >
              取消
            </button>
            <button
              type="button"
              class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-sm text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
              :disabled="!newSessionName.trim() || !newSessionDraft.trim() || creatingSession"
              @click="handleStartNewSessionFromSubject"
            >
              发送
            </button>
          </div>
        </div>

        <!-- 触发区 -->
        <button
          v-else
          type="button"
          class="w-full rounded-3xl bg-white px-4 py-4 text-left text-[#9ca3af] shadow-sm transition hover:bg-[#f9fafb]"
          @click="openCreatePanel"
        >
          在这个科目中新建会话...
        </button>
      </div>
    </div>
  </div>

  <ConfirmDialog
    v-if="confirmDelete"
    :title="'删除会话'"
    :message="`确定删除「${confirmDelete.name}」？会话内所有消息会被一并删除，操作不可恢复。`"
    :error="deleteError"
    :submitting="deleteSubmitting"
    @confirm="performDelete"
    @cancel="cancelDelete"
  />
</template>
