<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MessageContent from '../components/MessageContent.vue'
import SkillPicker from '../components/SkillPicker.vue'
import SkillChips from '../components/SkillChips.vue'
import {
  getErrorMessage,
  listDisplayMessages,
  listSessions,
  sendChatMessage,
  stopChatGeneration,
  type DisplayMessage,
  type ProjectItem,
  type SessionItem,
} from '../api'
import { type SkillMeta } from '../skills'
import { useAuth } from '../composables/useAuth'
import { useProjects } from '../composables/useProjects'
import { useProjectSkills } from '../composables/useProjectSkills'

const route = useRoute()
const router = useRouter()
const { projects, loadProjects } = useProjects()
const { preparing } = useAuth()

const errorMessage = ref('')

const pid = computed(() => route.params.pid as string)
const sid = computed(() => route.params.sid as string)
const currentProject = computed<ProjectItem | null>(
  () => projects.value.find((p) => p.pid === pid.value) ?? null,
)
const currentSession = ref<SessionItem | null>(null)

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

const isChatReady = computed(
  () => Boolean(currentProject.value && currentSession.value && !preparing.value),
)
const canSend = computed(() => Boolean(draft.value.trim() && isChatReady.value && !streaming.value))

// ── Skill 状态 ──────────────────────────────────────────────────────────────
// projectSkills 由共享 composable 提供，pid 变化或 App.vue 的对话框刷新时自动更新
const pidOrNull = computed(() => pid.value || null)
const { skills: projectSkills } = useProjectSkills(pidOrNull)
const selectedSkills = ref<SkillMeta[]>([])
const showSkillPicker = ref(false)

// ── 工具函数 ──────────────────────────────────────────────────────────────────
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

async function loadMessages(): Promise<void> {
  if (!currentSession.value) return
  messages.value = await listDisplayMessages(currentSession.value.sid)
  scrollToBottom(true)
}

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
      updateMessage(assistantId, {
        content:
          messages.value.find((message) => message.id === assistantId)?.content || '生成失败。',
      })
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
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void sendMessage()
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

// ── Drawer 动画 ─────────────────────────────────────────────────────────────
function onDrawerBeforeEnter(el: Element): void {
  const target = el as HTMLElement
  target.style.maxHeight = '0'
  target.style.opacity = '0'
}

function onDrawerEnter(el: Element, done: () => void): void {
  const target = el as HTMLElement
  requestAnimationFrame(() => {
    target.style.transition = 'max-height 220ms ease, opacity 180ms ease'
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
    target.style.transition = 'max-height 200ms ease, opacity 160ms ease'
    target.style.maxHeight = '0'
    target.style.opacity = '0'
    const handler = () => { target.removeEventListener('transitionend', handler); done() }
    target.addEventListener('transitionend', handler)
  })
}

// ── 挂载 / 销毁 ──────────────────────────────────────────────────────────────
async function validateAndLoad(): Promise<void> {
  // 阶段 1：确保项目列表可用，校验 pid 归属（失败 → 退回总览）
  try {
    if (projects.value.length === 0) await loadProjects()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
    await router.replace({ name: 'overview' })
    return
  }
  if (!currentProject.value) {
    await router.replace({ name: 'overview' })
    return
  }

  // 阶段 2：拉会话列表校验 sid（失败 → 退回科目页，附带错误信息）
  let match: SessionItem | undefined
  try {
    const allSessions = await listSessions(pid.value)
    match = allSessions.find((s) => s.sid === sid.value)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
    await router.replace({ name: 'subject', params: { pid: pid.value } })
    return
  }
  if (!match) {
    await router.replace({ name: 'subject', params: { pid: pid.value } })
    return
  }
  currentSession.value = match

  // 阶段 3：加载消息与项目技能。失败不离开视图，只在顶部显示错误，用户可手动重试。
  try {
    await loadMessages()
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  }
  // 项目技能由 useProjectSkills(pidOrNull) 的 watch 自动加载，这里不需要显式调用

  // 阶段 4：消费 SubjectView 传入的初始草稿并自动发送
  const initial = route.query.initial
  if (typeof initial === 'string' && initial.trim()) {
    draft.value = initial
    await router.replace({ name: 'chat', params: { pid: pid.value, sid: sid.value } })
    await nextTick()
    await sendMessage()
  }
}

onMounted(() => {
  void validateAndLoad()
  nextTick(autosizeComposer)
})

onBeforeUnmount(() => {
  currentAbort.value?.abort()
  if (copyResetTimer) window.clearTimeout(copyResetTimer)
})

watch(draft, () => { nextTick(autosizeComposer) })

watch(
  () => currentSession.value?.sessionname,
  (name) => {
    if (name && currentProject.value) {
      document.title = `${currentProject.value.projectname} / ${name} · Teachi`
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="absolute inset-0 flex flex-col">
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

    <footer class="flex-shrink-0 bg-[#f3f4f6] px-4 pb-4 pt-2">
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
      </div>
    </footer>
  </div>
</template>
