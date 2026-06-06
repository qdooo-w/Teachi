<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RowMenu from '../components/RowMenu.vue'
import RenameInline from '../components/RenameInline.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import SkillPicker from '../components/SkillPicker.vue'
import SkillChips from '../components/SkillChips.vue'
import {
  createSession,
  deleteSession,
  getErrorMessage,
  listSessions,
  renameSession,
  uploadAttachment,
  type ProjectItem,
  type SessionItem,
} from '../api'
import { useProjects } from '../composables/useProjects'
import { useLayout } from '../composables/useLayout'
import { useProjectSkills } from '../composables/useProjectSkills'
import { useUserSkills } from '../composables/useUserSkills'
import { readSkill, PROJECT_DESC_SKILL, parseSkillFile, type SkillMeta } from '../skills'
import {
  SUBJECT_DESC_COLLAPSE_LIMIT,
  CHAT_ATTACHMENT_MAX_BYTES,
  CHAT_DRAWER_ENTER_MAX_HEIGHT_MS,
  CHAT_DRAWER_ENTER_OPACITY_MS,
  CHAT_DRAWER_LEAVE_MAX_HEIGHT_MS,
  CHAT_DRAWER_LEAVE_OPACITY_MS,
} from '../config'

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
import { useNotification } from '../composables/useNotification'
const errorMessage = ref('')
const { showError } = useNotification()

watch(errorMessage, (newVal) => {
  if (newVal) {
    showError(newVal)
    errorMessage.value = ''
  }
})

// Store the created session ID so if uploads fail, retrying uses the same session
const createdSessionId = ref<string | null>(null)

// ── Skill 状态与逻辑 ─────────────────────────────────────────────────────────
const pidOrNull = computed(() => pid.value || null)
const { skills: projectSkills } = useProjectSkills(pidOrNull)
const { skills: userSkills, load: loadUserSkills } = useUserSkills()

interface ChatSkillMeta extends SkillMeta {
  rawName: string
  kind: 'user' | 'project'
}

const allSkills = computed<ChatSkillMeta[]>(() => {
  const pList = projectSkills.value.map((s) => ({
    ...s,
    name: `project-${s.name}`,
    rawName: s.name,
    display_name: `${s.display_name || s.name} [项目]`,
    kind: 'project' as const,
  }))
  const uList = userSkills.value.map((s) => ({
    ...s,
    name: `user-${s.name}`,
    rawName: s.name,
    display_name: `${s.display_name || s.name} [个人]`,
    kind: 'user' as const,
  }))
  return [...pList, ...uList]
})

const selectedSkills = ref<ChatSkillMeta[]>([])
const showSkillPicker = ref(false)

function toggleSkill(prefixedName: string): void {
  const skill = allSkills.value.find((s) => s.name === prefixedName)
  if (!skill) return
  const idx = selectedSkills.value.findIndex((s) => s.name === prefixedName)
  if (idx === -1) {
    selectedSkills.value.push(skill)
  } else {
    selectedSkills.value.splice(idx, 1)
  }
}

function removeSkill(prefixedName: string): void {
  selectedSkills.value = selectedSkills.value.filter((s) => s.name !== prefixedName)
}

function handlePickerToggle(name: string): void {
  toggleSkill(name)
  const el = messageInput.value
  if (el) {
    const pos = el.selectionStart ?? 0
    const before = el.value.slice(0, pos)
    const cleaned = before.replace(/(^|[\s\n])@([a-z0-9-]*)$/, '$1')
    if (cleaned !== before) {
      el.value = cleaned + el.value.slice(pos)
      newSessionDraft.value = el.value
      el.setSelectionRange(cleaned.length, cleaned.length)
    }
  }
}

function checkAtTrigger(): void {
  const el = messageInput.value
  if (!el) return
  const pos = el.selectionStart ?? 0
  const before = el.value.slice(0, pos)
  const match = before.match(/(^|[\s\n])@([a-z0-9-]*)$/)
  showSkillPicker.value = Boolean(match)
}

function handleComposerInput(): void {
  checkAtTrigger()
}

function handleComposerKeydown(event: KeyboardEvent): void {
  if (showSkillPicker.value && (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === 'Escape')) {
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void handleStartNewSessionFromSubject()
  }
}

// ── 附件状态与逻辑 ───────────────────────────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const pendingAttachments = ref<Array<{
  file: File
  temp_id: string
  original_filename: string
  mime_type: string
  uploading: boolean
  preview_url?: string
}>>([])

const ALLOWED_MIMES = new Set([
  'image/jpeg', 'image/png', 'image/webp', 'image/gif',
  'text/plain', 'text/markdown', 'text/csv', 'text/html',
  'application/json', 'application/pdf',
])

function triggerFileSelect(): void {
  fileInputRef.value?.click()
}

function addPendingFile(file: File): void {
  const limitMB = CHAT_ATTACHMENT_MAX_BYTES / (1024 * 1024)
  if (file.size > CHAT_ATTACHMENT_MAX_BYTES) {
    errorMessage.value = `"${file.name}" 大小超过 ${limitMB}MB 限制`
    return
  }
  const mime = file.type || 'application/octet-stream'
  if (!ALLOWED_MIMES.has(mime)) {
    errorMessage.value = `"${file.name}" 格式不支持（支持：图片、文本、JSON、PDF、CSV）`
    return
  }

  const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const preview_url = mime.startsWith('image/') ? URL.createObjectURL(file) : undefined
  pendingAttachments.value.push({
    file,
    temp_id: tempId,
    original_filename: file.name,
    mime_type: mime,
    uploading: false,
    preview_url,
  })
  errorMessage.value = ''
}

async function handleFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const files = Array.from(target.files)
  target.value = ''
  await Promise.all(files.map(addPendingFile))
}

async function handleComposerPaste(event: ClipboardEvent): Promise<void> {
  const items = event.clipboardData?.items
  if (!items) return
  const fileItems = Array.from(items).filter((item) => item.kind === 'file')
  if (fileItems.length === 0) return
  event.preventDefault()
  const files = fileItems.map((item) => item.getAsFile()).filter((f): f is File => f !== null)
  await Promise.all(files.map(addPendingFile))
}

async function handleComposerDrop(event: DragEvent): Promise<void> {
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  await Promise.all(Array.from(files).map(addPendingFile))
}

function removePendingAttachment(att: typeof pendingAttachments.value[0]): void {
  if (att.preview_url) {
    URL.revokeObjectURL(att.preview_url)
  }
  pendingAttachments.value = pendingAttachments.value.filter((item) => item.temp_id !== att.temp_id)
}

// ── Drawer 动画 ─────────────────────────────────────────────────────────────
function onDrawerBeforeEnter(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = '0'
  target.style.opacity = '0'
}

function onDrawerEnter(el: Element, done: () => void): void {
  const target = el as HTMLElement
  requestAnimationFrame(() => {
    target.style.transition = `max-height ${CHAT_DRAWER_ENTER_MAX_HEIGHT_MS}ms ease, opacity ${CHAT_DRAWER_ENTER_OPACITY_MS}ms ease`
    target.style.maxHeight = `${target.scrollHeight}px`
    target.style.opacity = '1'
    const handler = () => { target.removeEventListener('transitionend', handler); done() }
    target.addEventListener('transitionend', handler)
  })
}

function onDrawerAfterEnter(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = ''
  target.style.transition = ''
  target.style.opacity = ''
}

function onDrawerBeforeLeave(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = `${target.scrollHeight}px`
  target.style.opacity = '1'
}

function onDrawerLeave(el: Element, done: () => void): void {
  const target = el as HTMLElement
  requestAnimationFrame(() => {
    target.style.transition = `max-height ${CHAT_DRAWER_LEAVE_MAX_HEIGHT_MS}ms ease, opacity ${CHAT_DRAWER_LEAVE_OPACITY_MS}ms ease`
    target.style.maxHeight = '0'
    target.style.opacity = '0'
    const handler = () => { target.removeEventListener('transitionend', handler); done() }
    target.addEventListener('transitionend', handler)
  })
}

// ── 创建面板控制 ─────────────────────────────────────────────────────────────
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

  // 销毁预览资源
  for (const att of pendingAttachments.value) {
    if (att.preview_url) {
      URL.revokeObjectURL(att.preview_url)
    }
  }
  pendingAttachments.value = []
  selectedSkills.value = []
  createdSessionId.value = null
  showSkillPicker.value = false

  nextTick(() => {
    if (messageInput.value) messageInput.value.style.height = 'auto'
  })
}

// ── 项目简介 ──────────────────────────────────────────────────────────────────
const DESC_COLLAPSE_LIMIT = SUBJECT_DESC_COLLAPSE_LIMIT
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

  let activeSid = createdSessionId.value
  try {
    // 1. 创建会话（支持失败后重试不重复创会话）
    if (!activeSid) {
      const session = await createSession(pid.value, name)
      activeSid = session.sid
      createdSessionId.value = session.sid
      sessions.value = [session, ...sessions.value]
    }

    // 2. 依次串行上传附件
    const uploadedAttachmentsList: Array<{
      attachment_id: string
      temp_id: string
      original_filename: string
      mime_type: string
      preview_url?: string
    }> = []

    for (const att of pendingAttachments.value) {
      att.uploading = true
      try {
        const result = await uploadAttachment(activeSid, att.file)
        uploadedAttachmentsList.push({
          attachment_id: result.attachment_id,
          temp_id: att.temp_id,
          original_filename: result.original_filename,
          mime_type: result.mime_type,
          preview_url: att.preview_url,
        })
        att.uploading = false
      } catch (err) {
        att.uploading = false
        throw err // 抛出异常由外层 catch
      }
    }

    // 3. 构建 history state 传递给 ChatView
    const stateObj = {
      initialSkills: selectedSkills.value.map((s) => s.name),
      initialAttachments: uploadedAttachmentsList,
    }

    closeCreatePanel()

    await router.push({
      name: 'chat',
      params: { pid: pid.value, sid: activeSid },
      query: { initial: text },
      state: stateObj,
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
  await Promise.all([
    loadSessionsFor(pid.value),
    loadProjectDesc(pid.value),
    loadUserSkills(),
  ])
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

function autosizeMessageInput(): void {
  const el = messageInput.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

watch(newSessionDraft, () => {
  nextTick(autosizeMessageInput)
})

watch(
  () => currentProject.value?.projectname,
  (name) => {
    if (name) document.title = `${name} · Learnova`
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
              <div class="font-hans truncate font-medium text-[#1f2937]">{{ session.sessionname }}</div>
              <div class="font-hans mt-1 truncate text-xs text-[#9ca3af]">更新于 {{ formatDateTime(session.timestamp) }}</div>
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
        <!-- 创建面板：同一元素的展开/收起变换 -->
        <div
          class="create-panel"
          :class="{ expanded: showCreatePanel }"
          @click="!showCreatePanel && openCreatePanel()"
        >
          <!-- 收起态占位文字 -->
          <span class="create-placeholder">在这个科目中新建会话...</span>

          <!-- 展开态表单内容 -->
          <div class="create-fields">
            <div class="create-fields-inner flex flex-col">
              <input
                ref="sessionNameInput"
                v-model="newSessionName"
                type="text"
                class="w-full border-none bg-transparent py-2 text-base font-medium text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
                placeholder="会话名称"
                :disabled="creatingSession"
                @keydown.enter.prevent="messageInput?.focus()"
                @keydown.esc.prevent="closeCreatePanel"
                @click.stop
              />
              <div class="mx-2 border-t border-[#f3f4f6]" />

              <!-- Skill Chips -->
              <SkillChips
                v-if="selectedSkills.length > 0"
                :skills="selectedSkills"
                class="mt-1"
                @remove="removeSkill"
                @click.stop
              />

              <!-- Pending Attachments Previews -->
              <div v-if="pendingAttachments.length > 0" class="mb-2 mt-1 flex flex-wrap gap-2 px-1" @click.stop>
                <div
                  v-for="att in pendingAttachments"
                  :key="att.temp_id"
                  class="relative flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-2 py-1 text-xs text-[#374151]"
                >
                  <img
                    v-if="att.preview_url"
                    :src="att.preview_url"
                    class="h-6 w-6 rounded object-cover flex-shrink-0"
                    alt="Image preview"
                  />
                  <svg v-else class="h-3.5 w-3.5 text-[#6b7280]" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span class="max-w-[120px] truncate" :title="att.original_filename">{{ att.original_filename }}</span>
                  <span v-if="att.uploading" class="text-[10px] text-[#9ca3af] animate-pulse">上传中...</span>
                  <button
                    v-else
                    type="button"
                    class="flex h-4 w-4 items-center justify-center rounded-full text-[#9ca3af] hover:bg-[#e5e7eb] hover:text-[#1f2937]"
                    @click.stop="removePendingAttachment(att)"
                  >
                    <svg class="h-3 w-3" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>

              <textarea
                ref="messageInput"
                v-model="newSessionDraft"
                class="max-h-32 w-full resize-none border-none bg-transparent py-2 text-sm leading-normal text-[#1f2937] outline-none placeholder:text-[#9ca3af]"
                placeholder="输入第一条消息... (支持拖拽/粘贴文件，输入 @ 调用技能)"
                rows="2"
                :disabled="creatingSession"
                @keydown="handleComposerKeydown"
                @input="handleComposerInput"
                @click="checkAtTrigger"
                @paste="handleComposerPaste"
                @dragover.prevent
                @drop.prevent="handleComposerDrop"
                @click.stop
              />

              <!-- Skill Picker Drawer -->
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
                  :skills="allSkills"
                  :selected="selectedSkills.map((s) => s.name)"
                  class="my-2"
                  @toggle="handlePickerToggle"
                  @close="showSkillPicker = false"
                  @click.stop
                />
              </Transition>

              <div class="flex items-center justify-between pt-2">
                <div class="flex items-center gap-1">
                  <!-- 上传附件按钮 (Plus 符号) -->
                  <button
                    class="flex h-8 w-8 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="creatingSession"
                    title="上传附件"
                    type="button"
                    @click.stop="triggerFileSelect"
                  >
                    <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
                    </svg>
                  </button>

                  <input
                    ref="fileInputRef"
                    type="file"
                    class="hidden"
                    multiple
                    accept="image/jpeg,image/png,image/webp,image/gif,text/plain,text/markdown,text/csv,application/json,application/pdf"
                    @change="handleFileChange"
                  />

                  <!-- 添加技能按钮 (Paperclip 符号) -->
                  <button
                    class="flex h-8 w-8 items-center justify-center rounded-full text-[#6b7280] transition hover:bg-[#f3f4f6] hover:text-[#1f2937] disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="creatingSession"
                    title="添加技能"
                    type="button"
                    @click.stop="showSkillPicker = !showSkillPicker"
                  >
                    <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                  </button>
                </div>

                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="rounded-2xl px-4 py-2 text-sm text-[#6b7280] transition hover:bg-[#f3f4f6]"
                    :disabled="creatingSession"
                    @click.stop="closeCreatePanel"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    class="flex h-9 items-center justify-center gap-1 rounded-2xl border border-transparent bg-[#1f2937] px-5 text-sm text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:border-[#d1d5db] disabled:bg-white disabled:text-[#9ca3af]"
                    :disabled="!newSessionName.trim() || !newSessionDraft.trim() || creatingSession"
                    @click.stop="handleStartNewSessionFromSubject"
                  >
                    发送
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <Transition name="dialog-fade" appear>
    <ConfirmDialog
      v-if="confirmDelete"
      :title="'删除会话'"
      :message="`确定删除「${confirmDelete.name}」？会话内所有消息会被一并删除，操作不可恢复。`"
      :error="deleteError"
      :submitting="deleteSubmitting"
      @confirm="performDelete"
      @cancel="cancelDelete"
    />
  </Transition>
</template>

<style scoped>
/* ── 创建面板：同一元素的展开/收起变换 ── */
.create-panel {
  position: relative;
  cursor: pointer;
  border-radius: 1.5rem;
  background: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  padding: 1rem;
  overflow: hidden;
  /* transform 上移 + margin 补偿保持底部锚定 */
  transition:
    transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1),
    margin-bottom 0.4s cubic-bezier(0.2, 0.8, 0.2, 1),
    box-shadow 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
}

/* 展开：上边框向上移动，底部锚定 */
.create-panel.expanded {
  cursor: default;
  transform: translateY(-12px);
  margin-bottom: -12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

/* 占位文字：收起时可见，展开时淡出并收起高度 */
.create-placeholder {
  display: block;
  color: #9ca3af;
  transition: opacity 0.25s ease;
  opacity: 1;
  position: relative;
  z-index: 1;
}

.create-panel.expanded .create-placeholder {
  opacity: 0;
  height: 0;
  overflow: hidden;
}

/* 表单区域：grid 行高动画实现平滑展开/收起 */
.create-fields {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
  position: relative;
  z-index: 1;
}

.create-panel.expanded .create-fields {
  grid-template-rows: 1fr;
}

.create-fields-inner {
  overflow: hidden;
  min-height: 0;
}

/* 字段元素错开入场 */
.create-panel.expanded .create-fields-inner input,
.create-panel.expanded .create-fields-inner textarea {
  animation: create-field-in 0.35s cubic-bezier(0.2, 0.8, 0.2, 1) backwards;
}

.create-panel.expanded .create-fields-inner input {
  animation-delay: 0.08s;
}

.create-panel.expanded .create-fields-inner textarea {
  animation-delay: 0.14s;
}

.create-panel.expanded .create-fields-inner .pt-2 {
  animation: create-field-in 0.35s cubic-bezier(0.2, 0.8, 0.2, 1) 0.2s backwards;
}

@keyframes create-field-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 收起时字段淡出 */
.create-panel:not(.expanded) .create-fields-inner > * {
  opacity: 0;
  transition: opacity 0.2s ease;
}
</style>
