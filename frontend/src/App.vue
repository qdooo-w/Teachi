<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import MessageContent from './components/MessageContent.vue'
import {
  createNewChatSession,
  ensureChatWorkspace,
  getCurrentUserId,
  getErrorMessage,
  getStoredToken,
  listDisplayMessages,
  login,
  logout,
  refreshAccessToken,
  register as registerAccount,
  sendChatMessage,
  setStoredToken,
  stopChatGeneration,
  type DisplayMessage,
  type ProjectItem,
  type SessionItem,
} from './api'

const LAST_EMAIL_KEY = 'teachi.last_email'

const authMode = ref<'login' | 'register'>('login')
const authForm = reactive({
  username: '',
  email: localStorage.getItem(LAST_EMAIL_KEY) || '',
  password: '',
})

const token = ref<string | null>(getStoredToken())
const bootstrapping = ref(true)
const preparing = ref(false)
const authSubmitting = ref(false)
const streaming = ref(false)
const creatingSession = ref(false)
const errorMessage = ref('')
const authError = ref('')
const toolStatus = ref('')
const draft = ref('')

const currentProject = ref<ProjectItem | null>(null)
const currentSession = ref<SessionItem | null>(null)
const messages = ref<DisplayMessage[]>([])
const chatContainer = ref<HTMLElement | null>(null)
const currentAbort = ref<AbortController | null>(null)
const stickToBottom = ref(true)

const isAuthenticated = computed(() => Boolean(token.value))
const isChatReady = computed(() => Boolean(isAuthenticated.value && currentProject.value && currentSession.value && !preparing.value))
const displayUser = computed(() => {
  const currentToken = token.value
  const savedEmail = localStorage.getItem(LAST_EMAIL_KEY)
  const userId = currentToken ? getCurrentUserId() : null
  return savedEmail || (userId ? `${userId.slice(0, 8)}...` : '已登录')
})
const canSend = computed(() => Boolean(draft.value.trim() && isChatReady.value && !streaming.value))

function handleTokenChange(event: Event): void {
  token.value = (event as CustomEvent<string | null>).detail
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

async function loadMessages(): Promise<void> {
  if (!currentSession.value) return
  messages.value = await listDisplayMessages(currentSession.value.sid)
  scrollToBottom(true)
}

async function prepareChat(): Promise<void> {
  const userId = getCurrentUserId()
  if (!userId) {
    setStoredToken(null)
    throw new Error('无法从 access token 读取用户 ID。')
  }

  preparing.value = true
  errorMessage.value = ''

  try {
    const workspace = await ensureChatWorkspace(userId)
    currentProject.value = workspace.project
    currentSession.value = workspace.session
    await loadMessages()
  } finally {
    preparing.value = false
  }
}

async function initializeAuth(): Promise<void> {
  try {
    if (!getStoredToken() || !getCurrentUserId()) {
      await refreshAccessToken().catch(() => undefined)
    }

    token.value = getStoredToken()
    if (token.value) await prepareChat()
  } catch (error) {
    const message = getErrorMessage(error)
    errorMessage.value = message
    authError.value = message
    setStoredToken(null)
  } finally {
    bootstrapping.value = false
  }
}

async function submitAuth(): Promise<void> {
  authError.value = ''
  errorMessage.value = ''

  if (!authForm.email.trim() || !authForm.password.trim()) {
    authError.value = '请输入邮箱和密码。'
    return
  }

  if (authMode.value === 'register' && !authForm.username.trim()) {
    authError.value = '请输入用户名。'
    return
  }

  authSubmitting.value = true
  try {
    if (authMode.value === 'register') {
      await registerAccount(authForm.username.trim(), authForm.email.trim(), authForm.password)
    }

    await login(authForm.email.trim(), authForm.password)
    localStorage.setItem(LAST_EMAIL_KEY, authForm.email.trim())
    await prepareChat()
  } catch (error) {
    authError.value = getErrorMessage(error)
  } finally {
    authSubmitting.value = false
  }
}

async function handleLogout(): Promise<void> {
  await logout()
  currentAbort.value?.abort()
  currentProject.value = null
  currentSession.value = null
  messages.value = []
  draft.value = ''
  toolStatus.value = ''
  errorMessage.value = ''
  streaming.value = false
}

async function startNewSession(): Promise<void> {
  if (!currentProject.value || creatingSession.value || streaming.value) return

  creatingSession.value = true
  errorMessage.value = ''

  try {
    currentSession.value = await createNewChatSession(currentProject.value.pid)
    messages.value = []
    scrollToBottom(true)
  } catch (error) {
    errorMessage.value = getErrorMessage(error)
  } finally {
    creatingSession.value = false
  }
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

  const content = draft.value.trim()
  const now = Date.now() / 1000
  const userMessage: DisplayMessage = {
    id: `local-user-${Date.now()}`,
    role: 'user',
    content,
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
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void sendMessage()
  }
}

const composerTextarea = ref<HTMLTextAreaElement | null>(null)

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

onMounted(() => {
  window.addEventListener('teachi-token-change', handleTokenChange)
  void initializeAuth()
  nextTick(autosizeComposer)
})

onBeforeUnmount(() => {
  window.removeEventListener('teachi-token-change', handleTokenChange)
  currentAbort.value?.abort()
})
</script>

<template>
  <main class="h-full bg-[#f3f4f6] text-[#1f2937]">
    <section v-if="bootstrapping || (!isAuthenticated && !isChatReady)" class="flex h-full items-center justify-center px-4">
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

    <section v-else class="flex h-full flex-col">
      <header class="flex h-14 flex-shrink-0 items-center justify-between border-b border-[#d1d5db] bg-white px-4">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-bold">Teachi</span>
            <span v-if="preparing" class="text-xs text-[#6b7280]">准备中</span>
          </div>
          <div class="truncate text-xs text-[#6b7280]">
            {{ currentProject?.projectname || '默认学习项目' }} / {{ currentSession?.sessionname || '新的对话' }}
          </div>
        </div>

        <div class="flex items-center gap-1">
          <span class="hidden max-w-40 truncate px-2 text-xs text-[#6b7280] sm:inline">{{ displayUser }}</span>
          <button
            class="flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-[#4b5563] transition hover:border-[#d1d5db] hover:bg-[#f3f4f6] disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="creatingSession || streaming"
            title="新建对话"
            type="button"
            @click="startNewSession"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m7-7H5" />
            </svg>
          </button>
          <button
            class="flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-[#4b5563] transition hover:border-[#d1d5db] hover:bg-[#f3f4f6]"
            title="刷新消息"
            type="button"
            @click="loadMessages"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v6h6M20 20v-6h-6M20 9a8 8 0 0 0-14.9-4M4 15a8 8 0 0 0 14.9 4" />
            </svg>
          </button>
          <button
            class="flex h-9 w-9 items-center justify-center rounded-md border border-transparent text-[#4b5563] transition hover:border-[#d1d5db] hover:bg-[#f3f4f6]"
            title="退出登录"
            type="button"
            @click="handleLogout"
          >
            <svg class="h-4 w-4" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0-4-4m4 4H9m4 8H6a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3h7" />
            </svg>
          </button>
        </div>
      </header>

      <div ref="chatContainer" class="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6" @scroll.passive="handleChatScroll">
        <div class="mx-auto flex max-w-3xl flex-col gap-5 pb-4">
          <div v-if="messages.length === 0" class="mt-16 rounded-lg border border-dashed border-[#d1d5db] bg-white px-4 py-8 text-center text-sm text-[#6b7280]">
            还没有消息。
          </div>

          <div v-for="message in messages" :key="message.id" class="flex w-full flex-col">
            <div v-if="message.role === 'user'" class="flex justify-end">
              <div class="max-w-[85%] rounded-2xl border border-[#d1d5db] bg-[#f9fafb] px-5 py-3 text-[15px] leading-relaxed text-[#1f2937]">
                <p class="whitespace-pre-wrap break-words">{{ message.content }}</p>
              </div>
            </div>
            <div v-else class="flex justify-start">
              <div class="max-w-[85%] rounded-2xl border border-[#1f2937] bg-white px-5 py-4 text-[15px] leading-relaxed text-[#1f2937]">
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

          <div class="rounded-lg border border-[#1f2937] bg-white p-3 shadow-sm focus-within:ring-2 focus-within:ring-[#1f6f5b]/20">
            <textarea
              ref="composerTextarea"
              v-model="draft"
              class="composer-textarea w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-[#9ca3af]"
              :disabled="streaming || preparing"
              placeholder="给 Teachi 发送消息... (Enter 换行，Ctrl/⌘ + Enter 发送)"
              rows="2"
              @keydown="handleComposerKeydown"
            />
            <div class="mt-2 flex items-center justify-between">
              <div class="text-[10px] text-[#9ca3af]">Teachi 可能会犯错。请核查重要信息。</div>
              <button
                v-if="streaming"
                class="flex h-9 w-9 items-center justify-center rounded-md bg-[#9a3412] text-white transition hover:bg-[#7c2d12]"
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
                class="flex h-9 w-9 items-center justify-center rounded-md bg-[#1f2937] text-white transition hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#d1d5db] disabled:text-[#6b7280]"
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
    </section>
  </main>
</template>
